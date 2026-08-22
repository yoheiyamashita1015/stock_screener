# 米国株スクリーナー AWS移行構成・作成手順（現行実装準拠）

> この文書は`E:\Python\ClaudeTest\stock_screener`の2026年8月時点の
> ソースコードに合わせて更新しています。Pythonバッチ、local/S3保存層、
> Dockerfile、オフラインスクリーニング関数、Lambdaラッパーは実装済みです。
> ECR、ECS、EventBridge Scheduler、API Gateway、CloudFront、Web画面などの
> AWSリソースとフロントエンドは未作成です。

## 1. 目的

既存のPython製・米国株スクリーナーを、AWSの学習を兼ねてAWS上へ移行する。

主な特徴：

- Yahoo Finance（yfinance）から年次・四半期財務諸表と1年分の株価履歴を取得
- EPSの連続上昇
- 売上成長率
- その他の財務指標・株価指標
- ブラウザから条件を指定してスクリーニング
- 学習用・個人利用を前提とし、一般公開は当面しない
- なるべくシンプルかつ低コストな構成を優先する

---

# 2. 全体構成

```text
                     ┌─────────────────┐
                     │     Browser     │
                     └────────┬────────┘
                              │
                              ▼
                        CloudFront
                              │
                              ▼
                 S3（HTML / CSS / JS）
                              │
                              │ API呼び出し
                              ▼
                        API Gateway
                              │
                              ▼
                           Lambda
                    （スクリーニング）
                              │
                              ▼
                     S3 processed data


【財務データ更新】

EventBridge Scheduler
        │
        ▼
     ECS RunTask
        │
        ▼
     Fargate Task
        │
        ├── Yahoo Financeから取得
        ├── データ加工
        └── S3へ保存
                │
                ▼
        S3 raw / processed


【コンテナ・ログ】

Docker Image
    │
    ▼
   ECR

Fargate / Lambda
    │
    ▼
CloudWatch Logs
```

---

# 3. AWSサービスの役割

| サービス | 役割 |
|---|---|
| S3 | raw/processedデータの保存。将来は別バケットへWebファイルを保存 |
| CloudFront | S3上のWebサイトをHTTPSで配信 |
| API Gateway | ブラウザからLambdaを呼び出すHTTP API |
| Lambda | S3上の加工済みデータを使ってスクリーニング |
| ECS | Fargateタスクの管理 |
| Fargate | Yahoo Financeデータ取得の長時間バッチを実行。5,000銘柄なら実測換算で約11～12時間が目安 |
| ECR | Fargateで実行するDockerイメージを保存 |
| EventBridge Scheduler | 月1回などのタイミングでECS RunTaskを実行 |
| CloudWatch Logs | FargateやLambdaのログ確認 |
| IAM | 各AWSサービス間の権限管理 |
| VPC | Fargateのネットワーク |
| Public Subnet | FargateからYahoo Financeへ直接アウトバウンド通信 |
| Security Group | Fargateへの不要なインバウンド通信を遮断 |

---

# 4. 今回使わないもの

初期構成では以下は使わない。

- RDS
- DynamoDB
- NAT Gateway
- ALB
- EKS
- Step Functions
- SQS
- ElastiCache

理由：

- データ量が小さく、S3で十分
- スクリーニングはLambdaでファイルを読み込んで処理できる
- FargateはPublic Subnet + Public IPv4でYahoo Financeへ接続する
- NAT Gatewayは学習用構成では固定費が大きい
- バッチ処理はECS ServiceではなくECS RunTaskで十分

---

# 5. ネットワーク構成

```text
VPC
│
├── Internet Gateway
│
└── Public Subnet
      │
      └── Fargate Task
            │
            ├── Public IPv4
            │
            ├── Yahoo FinanceへHTTPS通信
            │
            └── S3へデータ保存
```

Fargateはインターネットからアクセスされる必要はないため、Security Groupでは基本的にインバウンド通信を許可しない。

アウトバウンド通信でYahoo Financeへアクセスする。

NAT Gatewayは使用しない。

---

# 6. データ構成

現行コードは、ローカルとS3で同じ相対キーを使用する。

```text
s3://<S3_BUCKET_NAME>/<S3_PREFIX>/

├── raw/
│   ├── AAPL.pkl
│   ├── MSFT.pkl
│   └── ...
└── processed/
    └── stocks.json
```

既定の`S3_PREFIX`は`stock-screener`なので、実際の例は次のようになる。

```text
s3://stock-screener-data-xxxx/stock-screener/raw/AAPL.pkl
s3://stock-screener-data-xxxx/stock-screener/processed/stocks.json
```

## raw

Yahoo Financeから取得した次の情報を、ticker単位のpickleとして保存する。

- `info`
- 年次・四半期の損益計算書、貸借対照表、キャッシュフロー
- 1年分の株価履歴
- tickerと取得日時

後から計算方法を変更した場合の再処理に利用できる。
pickleはPandas DataFrameを維持するために採用している。本バッチが生成した
信頼できるpickle以外は読み込まない。

## processed

Lambdaによるスクリーニングで直接利用する加工済みデータ。

`processed/stocks.json`は次の構造で保存する。

```json
{
  "generated_at": "2026-08-21T00:00:00+00:00",
  "count": 1,
  "stocks": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "sector": "Technology",
      "per": 28.1,
      "roe": 42.1,
      "revenue_growth": 8.5,
      "eps_growth_rate": 5.8,
      "eps_consecutive_years": 3,
      "current_price": 230.0,
      "rsi": 55.0,
      "trend_signal": "NEUTRAL"
    }
  ]
}
```

スクリーニング時に毎回数年分の財務データを再計算しない。

Yahoo Financeから取得したタイミングで、EPSのCAGR・連続増加年数、
ファンダメンタル指標、テクニカル指標をあらかじめ計算する。

現行の`revenue_growth`はyfinanceの`info.revenueGrowth`を百分率へ変換した値で、
複数年売上CAGRではない。EPSは年次損益計算書のBasic EPS（なければ
Diluted EPS）から`eps_growth_rate`（CAGR）と`eps_consecutive_years`を計算する。

---

# 7. データ更新頻度

Yahoo Financeのレート制限のため、全銘柄の財務データ取得は長時間になる。

原因はAWS側の性能ではなく、同一IPからの大量アクセスを避けるために
逐次取得と待機・リトライを行うためである。現行コードは60回/分を上限とし、
高レベルAPI呼び出しの開始間隔を最低1秒空ける。基本情報、株価履歴、
6種類の財務諸表の各取得に同じ制限を適用する。
429発生時は最大3試行とし、失敗後に60秒、120秒の指数バックオフを行う。

1銘柄につき高レベル取得は合計8回なので、60回/分では5,000銘柄で約11.1時間、
7,400銘柄で約16.4時間が最低目安になる。50銘柄・約400回のローカル実測は
約6分41秒で、429・リトライ・失敗はいずれも0件だった。対象銘柄数に応じて見積もる。

この60回/分はyfinanceの高レベル呼び出し開始回数に適用する。yfinance内部で
1回のプロパティ取得が複数のHTTP通信を行う可能性があるため、実際のHTTP通信を
厳密に60回/分へ固定するものではない。CloudWatch Logsで429を監視し、必要なら
`YAHOO_MAX_REQUESTS_PER_MINUTE`を10などへ下げる。

そのため高性能なFargateへ変更しても大幅な高速化は期待しない。

初期構成では以下を推奨。

```text
財務データ
EPS / 売上高 / 利益 / 数年分の推移
→ 月1回

株価など
→ 最初は同じく月1回でも可
→ 必要になれば将来、毎日更新へ分離
```

まずは「すべて月1回」でシンプルに完成させてもよい。

---

# 8. 長時間処理への対策

数十時間の処理途中で失敗しても、最初からやり直さなくて済むようにする。

現行コードではticker単位の保存を実装済みである。

- 取得成功直後に`raw/<ticker>.pkl`へ保存
- rawの最終更新日時が`RAW_MAX_AGE_HOURS`以内かつ必須データが揃っていれば再実行時にスキップ
- 既定値は672時間（28日）
- 古いrawは自動的に再取得
- `--force`を指定すると有効期間内でも再取得
- 基本情報、年次損益計算書、株価履歴のいずれかが不足するtickerは失敗として記録し、次へ継続
- 再取得失敗時も以前のrawは削除しないため、最終processedには最後に成功した
  データが残る場合がある。鮮度はrawの更新日時で確認する
- 不完全な新規rawは保存せず、不完全な既存rawも再取得対象にする
- 全ticker処理後、必須データが揃ったrawだけから`processed/stocks.json`を再生成

ログ例：

```text
Batch start
Target tickers: 5000

AAPL OK
MSFT OK
NVDA OK
XYZ ERROR: Too Many Requests

取得成功・途中保存 ticker=AAPL key=raw/AAPL.pkl
...
Batch finished
Success: 4988
Failed: 12
```

レート制限回避目的の大量並列化や複数IP利用は行わない。

---

# 9. Pythonコードの分割方針

既存コードは概念的に以下へ分離する。

```text
1. データ取得
2. データ加工
3. データ保存
4. スクリーニング
```

現行構成：

```text
project/
├── common/
│   ├── config.py
│   └── storage.py
│
├── src/
│   ├── data_fetcher.py
│   ├── fundamental.py
│   ├── technical.py
│   ├── fetch.py
│   ├── process.py
│   ├── validation.py
│   └── __init__.py
│
├── lambda_app/
│   ├── screen.py
│   └── README.md
│
├── web/
│   └── README.md
│
├── archive/legacy_streamlit/
│   └── 旧Streamlit UI・バックテスト
│
├── config.py
├── Dockerfile
├── requirements.txt
├── requirements.lock
├── .dockerignore
├── .gitignore
└── README.md
```

ただし、ファイルを細かく分けすぎない。

既存の計算式・スクリーニング条件・レート制限対策は可能な限り維持する。

---

# 10. ローカルとAWSの両対応

AWS専用コードにはせず、同じコードを以下で実行できるようにする。

```text
ローカルPython
ローカルDocker
ECS Fargate
```

保存先も切り替えられるようにする。

現行実装で利用する主な環境変数：

```text
STORAGE_MODE=local
S3_BUCKET_NAME=stock-screener-data-xxxx
S3_PREFIX=stock-screener
LOCAL_DATA_DIR=E:\Python\ClaudeTest\stock_screener\data
TICKER_FILE=
YAHOO_MAX_REQUESTS_PER_MINUTE=60
REQUEST_DELAY_SECONDS=3.0
REQUEST_JITTER_SECONDS=0.5
RETRY_MAX_ATTEMPTS=3
RETRY_WAIT_SECONDS=60
RAW_MAX_AGE_HOURS=672
CACHE_DIR=data/cache
LOG_LEVEL=INFO
```

`S3_PREFIX`には共通prefixを指定する。`raw/`や`processed/`はコードが後ろに
付加するため、`S3_PREFIX=processed/`とは設定しない。

ローカル：

```text
Python
↓
ローカルファイル
```

AWS：

```text
Fargate
↓
S3
```

AWS認証情報はコードへ直接記述しない。

FargateではECS Task Role、LambdaではLambda Execution Roleを使用する。

---

# 11. Fargateの使い方

今回のバッチではECS Serviceを作らない。

```text
EventBridge Scheduler
        │
        ▼
     ECS RunTask
        │
        ▼
     Fargate起動
        │
        ├── データ取得
        ├── 加工
        ├── S3保存
        │
        ▼
       終了
        │
        ▼
   Fargate Task停止
```

処理を実行している時間だけFargate料金が発生する。

初期スペック候補：

```text
0.5 vCPU
1 GB RAM
```

API待ち時間が長い処理なので、まず小さいスペックから試す。

メモリ不足の場合のみ増やす。

コンテナのENTRYPOINTは次のとおり。

```text
python -m src.fetch
```

ECS Task DefinitionのCommandには必要に応じて次の引数を設定する。

```text
--limit 10
--tickers AAPL,MSFT
--force
--no-technicals
--process-only
```

対象tickerは、`--tickers`、`TICKER_FILE`、自動取得した米国株一覧の順に
決定される。`--limit`は選択された一覧の先頭件数を制限する。

---

# 12. Webスクリーニング処理

ブラウザから条件を入力する。

例：

```text
PER上限          20
ROE下限          15
売上成長率下限   10
EPS連続上昇      3年

[検索]
```

ブラウザからAPI GatewayへJSONを送る。

```json
{
  "conditions": {
    "max_per": 20,
    "min_roe": 15,
    "min_revenue_growth": 10,
    "min_eps_consecutive_years": 3
  },
  "include_technicals": true
}
```

処理：

```text
Browser
↓
API Gateway
↓
Lambda
↓
S3 processedデータ取得
↓
Pythonで条件抽出
↓
JSON結果
↓
Browser
```

LambdaではYahoo Financeへアクセスしない。

スクリーニング関数は、外部I/Oを行わない純粋なPython関数として実装済みである。

実装済みの関数：

```python
from lambda_app.screen import lambda_handler, screen_stocks
```

Lambdaハンドラー名は`lambda_app.screen.lambda_handler`とする。直接イベントと、
API Gatewayから渡されるJSON文字列の`body`の両方を処理できる。

指定可能な条件名は現行の`ScreeningCriteria`に合わせる。

```text
min_market_cap / max_market_cap
min_per / max_per
min_pbr / max_pbr
min_dividend_yield / max_dividend_yield
min_roe / min_roa / min_revenue_growth
min_eps_growth / min_eps_consecutive_years
min_insider_hold / max_insider_hold / min_fcf_yield
min_rsi / max_rsi
above_sma_20 / above_sma_50 / above_sma_200
min_pct_from_52w_high / max_pct_from_52w_high
trend_signals / sectors / exclude_sectors
```

未対応の条件名を渡した場合は400を返す。正常時のレスポンスbodyは
`{"count": 件数, "stocks": [...]}`となる。

---

# 13. Webサイト

静的Webサイトは未実装である。同じリポジトリ内に、バックエンドとは独立した
`web/`ディレクトリとして作成する予定とする。

```text
web/
├── index.html
├── css/
│   └── style.css
└── js/
    └── app.js
```

公開構成：

```text
Browser
↓
CloudFront
↓
S3
```

S3バケット自体は公開せず、CloudFrontからのみアクセスできる構成にする。

CloudFrontではOAC（Origin Access Control）を利用する。

データ用S3とフロントエンド用S3は、権限を分かりやすくするため別バケットを
推奨する。現行Pythonコードが読み書きするのはデータ用バケットだけである。

---

# 14. 推奨する作成順序

現時点の進捗は次のとおり。

```text
STEP 1  Python整理             実装済み
STEP 2  ローカルPython確認     未実施（実行環境未導入）
STEP 3  Dockerfile作成         実装済み、build/run未確認
STEP 4以降 AWSリソース作成     未実施
```

## STEP 1：既存Pythonを整理（実装済み）

Codexを使って既存リポジトリを整理する。

確認事項：

- Yahoo Finance取得処理
- レート制限対策
- データ加工
- 保存
- スクリーニング
- エラー処理

AWSへ持っていきやすいコード構造への変更は完了している。

---

## STEP 2：ローカルでPythonを動作確認

```text
Yahoo Finance
↓
Python
↓
processedデータ作成
```

AWS導入前に正常動作を確認する。

まず少数銘柄で確認する。

```powershell
python -m pip install -r requirements.lock
$env:STORAGE_MODE = "local"
python -m src.fetch --tickers AAPL,MSFT
python -m lambda_app.screen --conditions '{"max_per":50,"min_roe":10}'
```

---

## STEP 3：Docker化（Dockerfile実装済み）

実装済みのDockerfileを使用する。

```powershell
docker build -t stock-screener-batch .
docker run --rm `
  -e STORAGE_MODE=local `
  -v "${PWD}/data:/app/data" `
  stock-screener-batch --tickers AAPL,MSFT
```

まずローカルDockerで正常に動くことを確認する。

---

## STEP 4：S3バケット作成

AWSマネジメントコンソールからS3バケットを作成。

例：

```text
stock-screener-data-xxxx
```

最初は手動でファイルをアップロードしてS3の基本操作を確認する。

---

## STEP 5：ローカルPython → S3

boto3を利用して、同じ取得バッチからrawとprocessedをS3へ保存できることを確認する。

```powershell
$env:STORAGE_MODE = "s3"
$env:S3_BUCKET_NAME = "stock-screener-data-xxxx"
$env:S3_PREFIX = "stock-screener"
python -m src.fetch --tickers AAPL,MSFT
```

ローカル確認時の認証情報はAWS CLIのプロファイルなどboto3の標準認証方法を
使用し、コードや`.env`へアクセスキーを記述しない。本番FargateではTask Roleを使う。

---

## STEP 6：ECRリポジトリ作成

AWSマネジメントコンソールでECRを作成する。

例：

```text
stock-screener-batch
```

---

## STEP 7：Docker ImageをECRへpush

ローカルPCで実施。

```text
docker build
↓
aws ecr get-login-password
↓
docker tag
↓
docker push
↓
ECR
```

---

## STEP 8：ECS / Fargateを作成

AWSマネジメントコンソールで以下を作成。

```text
ECS Cluster
Task Definition
Execution Role
Task Role
CloudWatch Logs
VPC / Public Subnet
Security Group
```

最初はEventBridge Schedulerを使わず、AWSコンソールから手動でRun Taskする。

目標：

```text
Run Task
↓
Fargate起動
↓
Yahoo Financeから取得
↓
S3へ保存
↓
正常終了
```

---

## STEP 9：CloudWatch Logs確認

Fargateからログが出ているか確認する。

確認内容：

```text
処理開始
現在ticker
取得成功
取得失敗
途中保存
処理終了
```

---

## STEP 10：EventBridge Scheduler

手動Run Taskが成功した後で自動化する。

例：

```text
毎月1日
↓
EventBridge Scheduler
↓
ECS RunTask
↓
Fargate
```

ここまででデータ更新基盤は完成。

---

## STEP 11：Lambdaでスクリーニング

まずAPI Gatewayを付けずLambda単体でテストする。

```text
S3
↓
Lambda
↓
スクリーニング
↓
結果
```

Lambdaテストイベント例：

```json
{
  "conditions": {
    "max_per": 20,
    "min_revenue_growth": 10
  },
  "include_technicals": true
}
```

Lambdaの環境変数には`STORAGE_MODE=s3`、`S3_BUCKET_NAME`、`S3_PREFIX`を設定し、
ハンドラーは`lambda_app.screen.lambda_handler`とする。

---

## STEP 12：API Gateway

Lambda単体が動いた後にAPI Gatewayを接続。

```text
POST /screen
↓
Lambda
```

curlやAPI Gatewayのテスト機能で確認する。

---

## STEP 13：Web画面作成

ローカルでHTML / CSS / JavaScriptを作る。

```text
検索条件
↓
JavaScript fetch()
↓
API Gateway
↓
結果をtable表示
```

---

## STEP 14：S3 + CloudFront

Web画面をS3へ配置し、CloudFront経由でアクセスする。

```text
Browser
↓
CloudFront
↓
S3 Web
↓
API Gateway
↓
Lambda
```

---

## STEP 15：IAM・監視・料金対策を整理

最後に権限やログを整理する。

例：

```text
Fargate Task Role
├── S3 ListBucket
└── S3 PutObject / GetObject

Lambda Execution Role
├── S3 GetObject
└── CloudWatch Logs

EventBridge Scheduler Role
├── ecs:RunTask
└── iam:PassRole（対象のExecution Role / Task Roleに限定）
```

必要最小限の権限へ変更する。

AWS Budgetsも設定し、予想外の課金を検知できるようにする。

---

# 15. 最初の到達目標

まずはここまでを第1フェーズとする。

```text
Python
↓
Docker
↓
ECR
↓
ECS Fargate
↓
Yahoo Finance
↓
S3
```

成功条件：

```text
AWSコンソールからRun Task
↓
Fargateが起動
↓
対象銘柄数に応じた長時間処理を実行（5,000銘柄なら約11～12時間が目安）
↓
S3にデータが保存
↓
Fargateが正常終了
↓
CloudWatch Logsで実行結果を確認
```

ここまで完成してからEventBridge SchedulerやWeb側へ進む。

---

# 16. 第2フェーズ

データ取得基盤完成後：

```text
S3 processed data
↓
Lambda
↓
API Gateway
↓
Web
↓
S3 + CloudFront
```

これで米国株スクリーナーWebアプリ全体が完成する。

---

# 17. コスト面の方針

主な料金はFargate。

5,000銘柄では約11～12時間、7,400銘柄では約16～17時間を見込むため、Fargate料金は
利用リージョン・CPU・メモリ構成と最新単価を使って事前に見積もる。

重要：

```text
NAT Gatewayは作らない
ECS Serviceで常駐させない
ALBは作らない
RDSは作らない
```

必要なときだけFargate Taskを起動する。

S3、Lambda、API Gateway、CloudFrontは個人利用程度なら大きな料金になりにくい。

AWS Budgetsを設定して予算超過を通知する。

---

# 18. 学習時に意識するポイント

単に「動いた」で終わらず、以下を理解する。

```text
S3
→ オブジェクトストレージとは何か

ECR
→ Docker Imageをどこに保存するのか

ECS
→ コンテナの管理とは何か

Fargate
→ EC2を管理せずコンテナを実行する仕組み

Task Definition
→ コンテナ実行設定

Execution Role
→ ECSがECRやCloudWatchを利用するための権限

Task Role
→ コンテナ内PythonがS3等へアクセスするための権限

EventBridge Scheduler
→ 定期的なECS RunTask

API Gateway
→ HTTP API

Lambda
→ サーバーレスなスクリーニング処理

CloudFront
→ 静的Webサイト配信

IAM
→ AWSサービス間の認可
```

---

# 19. 最終構成

```text
                     ┌─────────────────────┐
                     │       Browser       │
                     └──────────┬──────────┘
                                │
                                ▼
                           CloudFront
                                │
                                ▼
                        S3 Frontend
                     HTML / CSS / JS
                                │
                                ▼
                          API Gateway
                                │
                                ▼
                             Lambda
                     Screening Logic
                                │
                                ▼
                         S3 Processed
                                ▲
                                │
                                │
                     ┌──────────┴───────────┐
                     │                      │
              EventBridge Scheduler        │
                     │                      │
                     ▼                      │
                 ECS RunTask                │
                     │                      │
                     ▼                      │
              Fargate Task                  │
                     │                      │
              Yahoo Finance                 │
                     │                      │
              Data Processing ──────────────┘

Docker Image
    │
    ▼
   ECR

Fargate / Lambda
    │
    ▼
CloudWatch Logs
```

---

# 20. 作業順序の要約

```text
1. Codexで既存Python整理
2. ローカルPython動作確認
3. Docker化
4. S3作成
5. ローカルPython → S3
6. ECR作成
7. Docker ImageをECRへpush
8. ECS / Fargate作成
9. 手動Run Task
10. CloudWatch Logs確認
11. EventBridge Scheduler
12. Lambdaスクリーニング
13. API Gateway
14. Web画面
15. S3 + CloudFront
16. IAM・監視・料金対策整理
```

最初は「1〜10」までを第一目標にする。

現状はSTEP 1とDockerfileの作成まで完了している。次はPythonとDockerが
利用できる環境で、STEP 2の少数銘柄テストとSTEP 3のbuild/run確認を行う。
