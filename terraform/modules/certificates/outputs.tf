# ACM Certificate Module Outputs
# =============================================================================

output "certificate_arn" {
  description = "ARN of the ACM certificate"
  value       = aws_acm_certificate.c2_cert.arn
}

output "certificate_domain_name" {
  description = "Domain name of the certificate"
  value       = aws_acm_certificate.c2_cert.domain_name
}

output "certificate_status" {
  description = "Status of the certificate"
  value       = aws_acm_certificate.c2_cert.status
}

output "certificate_validation_status" {
  description = "Validation status after DNS validation"
  value       = aws_acm_certificate_validation.c2_cert.id != "" ? "VALIDATED" : "PENDING"
}

output "certificate_subject_alternative_names" {
  description = "Subject alternative names included in the certificate"
  value       = aws_acm_certificate.c2_cert.subject_alternative_names
}

output "validation_record_fqdns" {
  description = "FQDNs of the DNS validation records"
  value       = [for record in aws_route53_record.cert_validation : record.fqdn]
}

