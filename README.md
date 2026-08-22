# 米国株スクリーナー

Yahoo Financeからの取得・加工をECS Fargateのバッチとして実行し、
保存済みデータだけをLambdaなどからスクリーニングできる構成に整理した
プロジェクトです。旧Streamlit版は`archive/legacy_streamlit/`へ退避しています。

## 構成と処理フロー

```text
EventBridge Scheduler
        ↓
ECS RunTask / Fargate  (python -m src.fetch)
        ↓
Yahoo Finance（逐次取得、待機・リトライあり）
        ↓
raw/<ticker>.pkl       （1銘柄ごとの再開ポイント）
        ↓
processed/stocks.json  （計算済み指標）
        ↓
lambda_app.screen / Lambda（Yahoo Financeへ接続しない）
```

ローカル実行では`data/`、AWS実行では同じキー構成のS3を使います。

## ファイルの役割

- `src/data_fetcher.py`: 既存のYahoo Finance取得、キャッシュ、リトライ
- `src/fundamental.py`: 既存のEPS CAGR・連続増加年数などの計算
- `src/technical.py`: 既存のテクニカル指標計算
- `src/fetch.py`: Fargate向け逐次取得バッチと再開制御
- `src/process.py`: rawから既存分析ロジックを使ってprocessedを生成
- `src/validation.py`: 保存・再利用・加工前の必須データ検証
- `common/storage.py`: local/S3共通の読み書き
- `common/config.py`: Fargate/Lambda共通の環境変数設定
- `lambda_app/screen.py`: processedだけを使う純粋関数、CLI、Lambdaラッパー
- `web/`: 今後作成する静的フロントエンドの配置先
- `config.py`: 既存設定。主要な取得設定を環境変数で上書き可能
- `Dockerfile`: ECS RunTaskで終了するバッチコンテナ
- `requirements.lock`: 動作確認済み依存バージョンの固定一覧
- `archive/legacy_streamlit/`: Dockerでは使用しない旧UI・バックテスト一式

## 既存ロジックについて

EPSは年次`income_stmt`のBasic EPS（なければDiluted EPS）を古い順に並べ、
CAGRと直近からの連続増加回数を計算します。CAGRは期首・期末EPSがともに
正数の場合だけ計算し、赤字を含む場合は`null`にします。配当利回りは
`trailingAnnualDividendYield`の割合値を百分率へ変換し、二重の100倍を防ぎます。
その他の売上成長率、PER、PBR、ROE、ROA、FCF利回りなどは従来の計算です。

オフライン用`lambda_app.screen.matches_criteria`は、退避した旧
`StockScreener._matches_criteria`と同じ条件および欠損値の扱いです。

取得バッチは並列化しません。1 tickerずつ、基本情報、6種類の財務諸表、
1年の株価履歴という合計8回の高レベル取得を行います。Yahoo Financeへの各高レベル呼び出しは、
60回/分を上限として開始間隔を最低1秒空けます。429発生時は最大3試行の
指数バックオフを行います。

## 保存形式

```text
data/ または s3://<bucket>/<prefix>/
├ raw/
│  ├ AAPL.pkl
│  └ MSFT.pkl
└ processed/
   └ stocks.json
```

rawは、yfinanceが返す複数のPandas DataFrameを構造を変えずに保存できる
pickleにしました。このpickleは本バッチが生成した信頼できるデータだけを
読み込んでください。processedはLambdaで追加変換なしに読める標準JSONです。
NaNやnumpy固有型も標準JSON値へ変換して保存します。

rawは取得成功直後にticker単位で保存されます。通常の再実行では有効期間内の
rawをスキップするため、中断後も未取得tickerから続けられます。既定の有効期間
は28日なので、月次実行では古いrawが自動更新されます。有効期間内でも全件を
更新する場合だけ`--force`を指定します。基本情報、年次損益計算書、株価履歴の
いずれかが不足するrawは成功保存・再利用・processed出力の対象にしません。

## ローカルPython実行

Python 3.10以降を使用します。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
```

少数のtickerで取得を確認します。

```powershell
$env:STORAGE_MODE = "local"
$env:LOCAL_DATA_DIR = "E:\Python\ClaudeTest\stock_screener\data"
python -m src.fetch --tickers AAPL,MSFT
```

保存済みrawからprocessedだけを作り直す場合:

```powershell
python -m src.fetch --process-only
```

Yahoo Financeへ接続せず、保存済みデータを絞り込む場合:

```powershell
python -m lambda_app.screen --conditions '{"min_market_cap":1000000000,"max_per":50,"min_roe":10}'
```

旧Streamlit画面を再利用する場合の復元対象は
`archive/legacy_streamlit/README.md`に記載しています。

## tickerの指定

指定方法は次の優先順です。

1. `--tickers AAPL,MSFT`
2. `TICKER_FILE`で指定したUTF-8テキストまたはCSV
3. 既存`DataFetcher.get_us_stock_list()`が取得する米国株一覧

CSVには`ticker`または`symbol`列が必要です。テスト時は`--limit 10`の
ように対象数を制限できます。

## Docker実行

```powershell
docker build -t stock-screener-batch .
docker run --rm `
  -e STORAGE_MODE=local `
  -e YAHOO_MAX_REQUESTS_PER_MINUTE=60 `
  -v "${PWD}/data:/app/data" `
  stock-screener-batch --tickers AAPL,MSFT
```

コンテナのENTRYPOINTは`python -m src.fetch`です。`--tickers`などの引数は
その後ろに渡されます。バッチ完了後にPython
プロセスとコンテナは終了し、常駐しません。

## 環境変数

| 変数 | 既定値 | 用途 |
|---|---:|---|
| `STORAGE_MODE` | `local` | `local`または`s3` |
| `LOCAL_DATA_DIR` | `<project>/data` | ローカル保存先 |
| `S3_BUCKET_NAME` | なし | S3モードでは必須 |
| `S3_PREFIX` | `stock-screener` | S3内の共通prefix |
| `TICKER_FILE` | なし | ticker一覧ファイル |
| `YAHOO_MAX_REQUESTS_PER_MINUTE` | `60` | Yahoo Finance高レベル呼び出し上限（回/分） |
| `REQUEST_DELAY_SECONDS` | `1.0` | 呼び出し開始間隔。60回/分から求めた1秒未満にはならない |
| `REQUEST_JITTER_SECONDS` | `0` | 呼び出し間隔へ加えるランダムな待機の最大秒数 |
| `RAW_MAX_AGE_HOURS` | `672` | rawを再利用する最大時間（28日） |
| `RETRY_MAX_ATTEMPTS` | `3` | レート制限時の最大試行回数 |
| `RETRY_WAIT_SECONDS` | `60` | 最初のリトライ待機秒数 |
| `CACHE_DIR` | `data/cache` | 取得キャッシュとyfinance内部キャッシュの保存先 |
| `LOG_LEVEL` | `INFO` | ログレベル |

待機・リトライ値は、50銘柄・約400回の高レベル取得でエラーがなかった
「60回/分」という実測結果に合わせています。`REQUEST_DELAY_SECONDS`に1秒未満を
設定しても、60回/分の下限に補正されます。429が発生する環境では
`YAHOO_MAX_REQUESTS_PER_MINUTE=20`などへ下げてください。

この制限はyfinanceのプロパティ取得など、高レベル呼び出しの開始回数を
制御します。yfinanceが1回の高レベル呼び出し内部で実行するHTTP通信数までは
制御できないため、429ログを監視し、必要なら上限をさらに下げてください。

AWSアクセスキーやシークレットキーは設定しません。boto3の標準認証解決に
より、ECS Task RoleまたはLambda Execution Roleを使用します。

## ECS Fargateの設定

- 起動方式: ECS ServiceではなくEventBridge SchedulerからECS RunTask
- コンテナ: ECRへ登録した本Dockerイメージ
- ネットワーク: Public Subnet、Public IPv4割り当てあり
- Security Group: インバウンド不要、HTTPSのアウトバウンドを許可
- ログドライバー: `awslogs`でCloudWatch Logsへ送信
- タスク環境変数: `STORAGE_MODE=s3`、`S3_BUCKET_NAME`、必要なら
  `S3_PREFIX`、待機・リトライ・ログ設定
- Task Role: 下記S3権限
- Task Execution Role: ECRイメージ取得とCloudWatch Logs出力権限

Task Roleの最小例です。バケット名とprefixを置き換えてください。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["stock-screener/*"]
        }
      }
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/stock-screener/*"
    }
  ]
}
```

## Lambdaからの利用

ハンドラーは次を指定できます。

```text
lambda_app.screen.lambda_handler
```

中心ロジックは外部I/Oを行わない次の関数です。

```python
from lambda_app.screen import screen_stocks

result = screen_stocks(processed_data, {"min_roe": 10})
```

Lambda Execution Roleには、processed JSONを読むための
`s3:GetObject`を`<prefix>/processed/stocks.json`へ付与します。
API Gatewayからのイベントでは、bodyに次のようなJSONを渡します。

```json
{
  "conditions": {
    "min_market_cap": 1000000000,
    "max_per": 50,
    "min_roe": 10
  },
  "include_technicals": true
}
```

API Gateway、静的Web画面、CloudFront自体は今回の範囲には含めていません。
