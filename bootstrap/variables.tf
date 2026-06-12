variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Terraform stateを保存するS3バケット名（グローバルで一意）"
}

variable "lock_table_name" {
  type    = string
  default = "terraform-locks"
}
