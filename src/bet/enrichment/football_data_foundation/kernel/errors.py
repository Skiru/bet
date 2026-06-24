from __future__ import annotations

class EvidenceKernelError(ValueError):
    pass


class CredentialsMissingError(EvidenceKernelError):
    pass


class ProviderCapabilityError(EvidenceKernelError):
    pass


class ProofLevelViolation(EvidenceKernelError):
    pass


class PayloadPolicyViolation(EvidenceKernelError):
    pass


class FreshnessViolation(EvidenceKernelError):
    pass


class IdentityMappingViolation(EvidenceKernelError):
    pass


class FusionNotAllowedError(EvidenceKernelError):
    pass
