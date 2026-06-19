# CI/CD ワークフロー仕様

本プロジェクトで使用している GitHub Actions ワークフローの仕様です。

---

## 1. テスト (`workflows/test.yml`)

### 概要

push および Pull Request 時にユニットテストを自動実行し、複数の OS・Python バージョンの組み合わせで動作を検証します。

### トリガー

| イベント | 対象ブランチ |
|---|---|
| `push` | `main`, `master` |
| `pull_request` | `main`, `master` |

### テストマトリクス

| OS | Python バージョン |
|---|---|
| `ubuntu-latest` | 3.9, 3.10, 3.11, 3.12, 3.13 |
| `windows-latest` | 3.9, 3.10, 3.11, 3.12, 3.13 |
| `macos-latest` | 3.9, 3.10, 3.11, 3.12, 3.13 |

合計 **15 パターン** で実行されます。

### 設定

- **`fail-fast: false`** — 1つの組み合わせが失敗しても、他の組み合わせのテストは継続します。これにより、特定環境でのみ発生する問題を見逃さずに検出できます。

### 実行ステップ

| # | ステップ | 内容 |
|---|---|---|
| 1 | `actions/checkout@v4` | リポジトリをチェックアウト |
| 2 | `actions/setup-python@v5` | 指定バージョンの Python をセットアップ |
| 3 | `pip install -e ".[dev]"` | パッケージ本体 + 開発用依存（pytest）をインストール |
| 4 | `pytest -v` | ユニットテストを詳細出力で実行 |

### 成功条件

全 15 パターンで `pytest` が終了コード 0（全テスト合格）を返すこと。

---

## 2. PyPI 公開 (`workflows/publish.yml`)

### 概要

GitHub Release を作成した際に、パッケージを自動ビルドして PyPI に公開します。

### トリガー

| イベント | 条件 |
|---|---|
| `release` | `types: [published]`（Release が公開された時） |

### 認証方式

**Trusted Publisher（OIDC）** を使用します。API トークンの管理が不要で、GitHub と PyPI 間で安全に認証されます。

#### PyPI 側の事前設定

1. https://pypi.org/manage/project/pypamc-204/settings/publishing/ を開く
2. 以下を登録する：

| 項目 | 値 |
|---|---|
| Owner | `mechano-transformer` |
| Repository name | `PAMC-204` |
| Workflow name | `publish.yml` |
| Environment | （空欄のまま） |

### 実行ステップ

| # | ステップ | 内容 |
|---|---|---|
| 1 | `actions/checkout@v4` | リポジトリをチェックアウト |
| 2 | `actions/setup-python@v5` | Python 3.13 をセットアップ |
| 3 | `pip install build` | ビルドツールをインストール |
| 4 | `python -m build` | sdist + wheel を `dist/` に生成 |
| 5 | `pypa/gh-action-pypi-publish@release/v1` | `dist/` 内のファイルを PyPI にアップロード |

### 権限

```yaml
permissions:
  id-token: write
```

OIDC トークンの発行に必要です。この権限がないと Trusted Publisher 認証が失敗します。

### リリース手順

1. `pyproject.toml` と `src/pypamc204/__init__.py` のバージョンを更新する
2. 変更をコミット・push する
3. GitHub 上で Release を作成する（タグ例: `v0.2.0`）
4. ワークフローが自動で起動し、PyPI に公開される

---

## ワークフロー間の関係

```
push / PR → [test.yml] テスト実行（15パターン）
                ↓ テスト合格を確認
          Release 作成
                ↓
         [publish.yml] PyPI 公開
```

テストワークフローは公開ワークフローの前提条件ではありませんが、Release を作成する前に PR のテストが全て合格していることを確認してください。
