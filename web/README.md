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

## UI機能

- 主要条件を常時表示し、補助条件を`Add filter`から追加
- 検索レスポンスの`generated_at`を株式データの最終取得日時として日本時間で表示
- テーブルヘッダーによる昇順・降順の切り替え
- フィルター名とテーブル列名にマウスを重ねた際の指標説明
- 50件単位のページング
- 検索条件の名前付き保存・読み込み・削除

保存済み条件はブラウザのlocalStorageにだけ保存します。保存キーは
`stock-compass.saved-filters.v1`です。APIの検索結果や株式データは保存しません。
同名で保存する場合は確認後に上書きします。保存データのJSONが破損している場合は、
該当キーを初期化してスクリーナー自体の動作を継続します。

現行APIが対応していない営業利益率・株価による絞り込みや、時系列財務データの
詳細画面は実装していません。Tickerと企業名はYahoo Financeの詳細ページへリンクします。

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
