variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "bucket_name" {
  type        = string
  description = "学習用S3バケット名（グローバルで一意）"
}
