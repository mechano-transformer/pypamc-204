# PyPI公開手順書

`pypamc_204` パッケージを PyPI に登録し、第三者が `pip install pypamc_204` でインストールできるようにする手順です。

---

## 1. 事前準備

### 1.1 PyPIアカウント作成

1. https://pypi.org/account/register/ にアクセス
2. ユーザー名・メールアドレス・パスワードを入力して登録
3. メール認証を完了する

### 1.2 APIトークンの発行

1. https://pypi.org/manage/account/#api-tokens にアクセス
2. 「Add API token」をクリック
3. Token name: 任意（例: `pypamc_204`）
4. Scope: 初回は「Entire account」を選択（パッケージ登録後にスコープを限定可能）
5. 発行されたトークン（`pypi-` で始まる文字列）を安全な場所に保存

### 1.3 テスト用PyPIアカウント（推奨）

本番登録前にテストしたい場合、TestPyPI を使用します。

1. https://test.pypi.org/account/register/ でアカウント作成（本番とは別アカウント）
2. 同様にAPIトークンを発行

---

## 2. ビルドツールのインストール

```bash
pip install build twine
```

| ツール | 用途 |
|--------|------|
| `build` | sdist / wheel の作成 |
| `twine` | PyPI へのアップロード |

---

## 3. パッケージのビルド

プロジェクトルートで実行します。

```bash
cd pypamc-204
python -m build
```

成功すると `dist/` フォルダに以下が生成されます：

```
dist/
├── pypamc_204-0.1.0.tar.gz        # ソース配布物 (sdist)
└── pypamc_204-0.1.0-py3-none-any.whl  # ホイール (wheel)
```

---

## 4. アップロード前の確認

```bash
twine check dist/*
```

`PASSED` と表示されればOKです。

---

## 5. TestPyPI へのテストアップロード（推奨）

本番前にテスト環境で確認します。

### 5.1 アップロード

```bash
twine upload --repository testpypi dist/*
```

ユーザー名・パスワードを求められた場合：

| 項目 | 入力値 |
|------|--------|
| Username | `__token__` |
| Password | 発行したAPIトークン（`pypi-...` の文字列全体） |

### 5.2 テストインストールで動作確認

```bash
pip install --index-url https://test.pypi.org/simple/ pypamc_204
```

```python
python -c "from pypamc204 import PAMC204; print('OK')"
```

---

## 6. 本番PyPIへのアップロード

```bash
twine upload dist/*
```

| 項目 | 入力値 |
|------|--------|
| Username | `__token__` |
| Password | 本番PyPIのAPIトークン |

成功すると以下のURLで公開されます：

```
https://pypi.org/project/pypamc_204/
```

---

## 7. インストール確認

```bash
pip install pypamc_204
```

```python
from pypamc204 import PAMC204
print("インストール成功")
```

---

## 8. バージョン更新時の手順

新バージョンをリリースする場合：

### 8.1 バージョン番号を更新

2箇所を同じバージョンに揃えます：

**pyproject.toml:**
```toml
version = "0.2.0"
```

**src/pypamc204/\_\_init\_\_.py:**
```python
__version__ = "0.2.0"
```

### 8.2 古いビルドを削除してから再ビルド・アップロード

```bash
rm -rf dist/
python -m build
twine check dist/*
twine upload dist/*
```

> PyPI は同じバージョン番号での上書きを許可しません。必ずバージョンを上げてください。

---

## 9. 認証情報の永続化（任意）

毎回トークンを入力したくない場合、`~/.pypirc` に保存できます。

```ini
[pypi]
username = __token__
password = pypi-ここにトークンを貼る

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-ここにテスト用トークンを貼る
```

> **注意:** このファイルにはAPIトークンが平文で保存されます。ファイルの権限を制限してください。
>
> ```bash
> chmod 600 ~/.pypirc
> ```

---

## 10. トラブルシューティング

| 症状 | 原因と対処 |
|------|-----------|
| `HTTPError: 400 Bad Request` | パッケージ名が既に使われている → `pyproject.toml` の `name` を変更 |
| `HTTPError: 403 Forbidden` | トークンが無効 → PyPIで再発行 |
| `File already exists` | 同じバージョンを再アップロードしようとしている → バージョン番号を上げる |
| `InvalidDistribution` | `twine check` でエラー → `pyproject.toml` や `README.md` を修正 |
| `twine` が見つからない | `pip install twine` を再実行 |

---

## GitHub Actions による自動公開（推奨）

APIトークンの管理が不要な **Trusted Publisher（OIDC）** 方式です。
GitHub Release を作成するだけで PyPI に自動公開されます。

### 事前設定（初回のみ）

1. https://pypi.org/manage/project/pypamc-204/settings/publishing/ を開く
2. 「Add a new publisher」に以下を入力して保存：

| 項目 | 値 |
|------|-----|
| Owner | `mechano-transformer` |
| Repository name | `pypamc-204` |
| Workflow name | `publish.yml` |
| Environment name | （空欄のまま） |

### リリース手順

1. `pyproject.toml` と `src/pypamc204/__init__.py` のバージョンを更新する
2. 変更をコミット・push する
3. GitHub 上で Release を作成する（タグ例: `v0.2.0`）
4. `publish.yml` が自動で起動し、ビルド → PyPI 公開が行われる

> トークンの発行・管理・ローテーションは一切不要です。
> GitHub と PyPI が OIDC で直接認証します。

---

## クイックリファレンス

### 手動公開（twine）

```bash
pip install build twine
python -m build
twine check dist/*
twine upload dist/*
```

### 自動公開（GitHub Actions）

```
1. バージョン更新 → commit → push
2. GitHub で Release 作成
3. 自動で PyPI に公開される
```
