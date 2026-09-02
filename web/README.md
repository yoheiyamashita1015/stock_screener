# Webフロントエンド

API Gatewayの`POST /screen`を呼び出し、Lambdaのスクリーニング結果を
表示する静的Webフロントエンドです。

構成:

```text
web/
├ index.html
├ css/
│  └ style.css
└ js/
   └ app.js
```

WebはAPI Gatewayへスクリーニング条件を送り、Lambdaから返された結果を
表示します。EPSや売上成長率の計算、銘柄の条件判定はWeb側へ実装しません。

## ローカル確認

プロジェクトルートで次を実行します。

```bash
python3 -m http.server 8080 --directory web
```

ブラウザで`http://localhost:8080`を開きます。API Gateway側で
`http://localhost:8080`または`*`をCORSの許可オリジンに設定してください。

API URLを変更する場合は、`js/app.js`冒頭の`API_URL`を更新します。

## 公開前の確認

- API GatewayのCORSをCloudFrontの配信ドメインへ限定する
- API GatewayとLambdaのスロットリング・監視を確認する
- `index.html`のContent Security Policyに新しいAPI URLを反映する
