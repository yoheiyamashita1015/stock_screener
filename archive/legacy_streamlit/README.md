# 旧Streamlit版の退避ファイル

このディレクトリには、現在のDocker/Fargateバッチでは使用しない旧UIと
バックテスト関連ファイルを退避しています。削除はしていません。

## 退避内容

- `app.py`: Streamlit画面
- `run.bat`: Streamlit起動用バッチ
- `requirements-ui.txt`: UI用の追加依存関係
- `ROADMAP.md`: 旧Web/API構想
- `src/screener.py`: 取得と画面用スクリーニングをまとめた旧エンジン
- `src/backtest.py`: 旧バックテスト処理

## 元の場所へ戻す場合

```text
archive/legacy_streamlit/app.py                 -> app.py
archive/legacy_streamlit/run.bat                -> run.bat
archive/legacy_streamlit/requirements-ui.txt    -> requirements-ui.txt
archive/legacy_streamlit/ROADMAP.md             -> ROADMAP.md
archive/legacy_streamlit/src/screener.py        -> src/screener.py
archive/legacy_streamlit/src/backtest.py        -> src/backtest.py
```

復元後、UI用依存関係をインストールして起動します。

```powershell
python -m pip install -r requirements-ui.txt
streamlit run app.py
```
