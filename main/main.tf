locals {
  prefix = "${var.env}-learn"
}

# 学習用S3バケット
resource "aws_s3_bucket" "learn" {
  bucket = var.bucket_name

  tags = {
    test = "foo"
  }
}

resource "aws_s3_bucket_public_access_block" "learn" {
  bucket                  = aws_s3_bucket.learn.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
