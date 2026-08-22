# Webフロントエンド配置先

静的Webページを作成する際は、このディレクトリ以下へ配置します。

予定構成:

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
