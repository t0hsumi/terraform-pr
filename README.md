# Terraform AWS 学習環境

コスト最小のTerraform学習用セットアップ。  
AWSコンソールで変更して `terraform plan` で差分を確認するワークフローを想定。

## ディレクトリ構成

```
.
├── bootstrap/   # Terraformのstate管理インフラ（初回のみ手動apply）
└── main/        # 実際の学習リソース
```

## 初回セットアップ

### 前提

- AWS CLIインストール済み・認証設定済み（`aws configure` or 環境変数）
- Terraform >= 1.6 インストール済み

### 1. State管理インフラを作る（bootstrap）

```bash
cd bootstrap
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集: state_bucket_name をユニークな名前に変える
vim terraform.tfvars

terraform init
terraform apply
```

### 2. main/providers.tf のバックエンドを更新

`main/providers.tf` の `backend "s3"` ブロックの `bucket` を  
bootstrapで作ったバケット名に書き換える。

### 3. 学習用リソースをデプロイ

```bash
cd ../main
cp terraform.tfvars.example terraform.tfvars
# terraform.tfvars を編集: bucket_name をユニークな名前に変える
vim terraform.tfvars

terraform init
terraform apply
```

## 学習ワークフロー

```bash
# コンソールでリソースを変更した後、差分確認
terraform plan

# Terraformに状態を同期させる
terraform apply
```

## コスト試算

| リソース | 料金 |
|---------|------|
| S3バケット（state用）| ほぼ0円（数KB程度） |
| DynamoDB（ロック用）| 0円（PAY_PER_REQUEST、ほぼ使われない） |
| S3バケット（学習用）| 0円（空なら） |
| 合計 | **月数円以下** |
