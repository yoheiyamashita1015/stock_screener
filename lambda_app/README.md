# スクリーニング用Lambda

`screen.py`はS3の`processed/stocks.json`を読み込み、指定条件で銘柄を
絞り込むLambdaコードです。Yahoo Financeには接続しません。

ハンドラー:

```text
lambda_app.screen.lambda_handler
```

Lambdaのデプロイ成果物には次を含めます。

```text
lambda_app/
common/
config.py
```

Lambda処理はPandasやyfinanceを使用しません。S3アクセスにはLambda Python
ランタイムに含まれるboto3を使用します。バッチ用`requirements.txt`全体を
Lambdaへ同梱する必要はありません。

環境変数:

```text
STORAGE_MODE=s3
S3_BUCKET_NAME=...
S3_PREFIX=stock-screener
LOG_LEVEL=INFO
```

ローカルで保存済みデータを絞り込む場合:

```powershell
python -m lambda_app.screen --conditions '{"max_per":50,"min_roe":10}'
```
