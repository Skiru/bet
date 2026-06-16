from __future__ import annotations
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from bet.enrichment.kernel.codec import canonical_sha256

def _validate_sha256(val: object, name: str) -> None:
    if type(val) is not str:
        raise TypeError(f"{name} must be exact str")
    if len(val) != 64:
        raise ValueError(f"{name} must be 64 characters long")
    if not all(c in "0123456789abcdef" for c in val):
        raise ValueError(f"{name} must be lowercase 64-hex SHA-256")

def _validate_exact_string(val: object, name: str) -> None:
    if type(val) is not str:
        raise TypeError(f"{name} must be exact str")
    if not val:
        raise ValueError(f"{name} cannot be empty")

def runtime_code_digest(
    *,
    git_commit_sha: str,
    git_tree_sha: str,
    dirty: bool,
    wheel_sha256: str,
    lock_sha256: str,
    bundle_root_sha256: str,
    package_version: str,
) -> str:
    _validate_sha256(git_commit_sha, "git_commit_sha")
    _validate_sha256(git_tree_sha, "git_tree_sha")
    if type(dirty) is not bool:
        raise TypeError("dirty must be exact bool")
    if dirty is not False:
        raise ValueError("dirty must be exact False")
    _validate_sha256(wheel_sha256, "wheel_sha256")
    _validate_sha256(lock_sha256, "lock_sha256")
    _validate_sha256(bundle_root_sha256, "bundle_root_sha256")
    _validate_exact_string(package_version, "package_version")

    return canonical_sha256({
        "profile": "BET-RUNTIME-CODE-1",
        "git_commit_sha": git_commit_sha,
        "git_tree_sha": git_tree_sha,
        "dirty": dirty,
        "wheel_sha256": wheel_sha256,
        "lock_sha256": lock_sha256,
        "bundle_root_sha256": bundle_root_sha256,
        "package_version": package_version,
    })

def runtime_environment_digest(
    *,
    environment: str,
    python_implementation: str,
    python_version: str,
    os_name: str,
    os_release: str,
    machine: str,
    sqlite_version: str,
    sqlite_compile_options: tuple[str, ...],
    tzdb_version: str,
    locale: str,
    lock_hash: str,
    feature_flag_hash: str,
    secret_identifiers: tuple[str, ...],
) -> str:
    _validate_exact_string(environment, "environment")
    _validate_exact_string(python_implementation, "python_implementation")
    _validate_exact_string(python_version, "python_version")
    _validate_exact_string(os_name, "os_name")
    _validate_exact_string(os_release, "os_release")
    _validate_exact_string(machine, "machine")
    _validate_exact_string(sqlite_version, "sqlite_version")

    if type(sqlite_compile_options) is not tuple:
        raise TypeError("sqlite_compile_options must be tuple")
    for item in sqlite_compile_options:
        if type(item) is not str or not item:
            raise TypeError("sqlite_compile_options elements must be non-empty str")
    if list(sqlite_compile_options) != sorted(set(sqlite_compile_options)):
        raise ValueError("sqlite_compile_options must be sorted and duplicate-free")

    _validate_exact_string(tzdb_version, "tzdb_version")
    _validate_exact_string(locale, "locale")
    _validate_sha256(lock_hash, "lock_hash")
    _validate_sha256(feature_flag_hash, "feature_flag_hash")

    if type(secret_identifiers) is not tuple:
        raise TypeError("secret_identifiers must be tuple")
    for item in secret_identifiers:
        if type(item) is not str or not item:
            raise TypeError("secret_identifiers elements must be non-empty str")
    if list(secret_identifiers) != sorted(set(secret_identifiers)):
        raise ValueError("secret_identifiers must be sorted and duplicate-free")

    return canonical_sha256({
        "profile": "BET-RUNTIME-ENV-1",
        "environment": environment,
        "python_implementation": python_implementation,
        "python_version": python_version,
        "os_name": os_name,
        "os_release": os_release,
        "machine": machine,
        "sqlite_version": sqlite_version,
        "sqlite_compile_options": sqlite_compile_options,
        "tzdb_version": tzdb_version,
        "locale": locale,
        "lock_hash": lock_hash,
        "feature_flag_hash": feature_flag_hash,
        "secret_identifiers": secret_identifiers,
    })

def request_identity(
    *,
    sport: str,
    target_event_entity_id: int,
    quality_profile: str,
    capability_keys: tuple[str, ...],
    effective_cutoff_at: datetime,
    refresh_nonce: str | None,
    consumer_contract_version: str,
) -> str:
    _validate_exact_string(sport, "sport")
    if type(target_event_entity_id) is not int or isinstance(target_event_entity_id, bool) or target_event_entity_id <= 0:
        raise TypeError("target_event_entity_id must be positive int")
    _validate_exact_string(quality_profile, "quality_profile")

    if type(capability_keys) is not tuple:
        raise TypeError("capability_keys must be tuple")
    for item in capability_keys:
        if type(item) is not str or not item:
            raise TypeError("capability_keys elements must be non-empty str")
    if list(capability_keys) != sorted(set(capability_keys)):
        raise ValueError("capability_keys must be sorted and duplicate-free")

    if type(effective_cutoff_at) is not datetime:
        raise TypeError("effective_cutoff_at must be datetime")
    if effective_cutoff_at.tzinfo is None or effective_cutoff_at.utcoffset() is None:
        raise ValueError("effective_cutoff_at must be timezone-aware")

    if refresh_nonce is not None:
        if type(refresh_nonce) is not str or not refresh_nonce:
            raise TypeError("refresh_nonce must be non-empty str or None")

    _validate_exact_string(consumer_contract_version, "consumer_contract_version")

    return canonical_sha256({
        "profile": "BET-REQUEST-1",
        "sport": sport,
        "target_event_entity_id": target_event_entity_id,
        "quality_profile": quality_profile,
        "capability_keys": capability_keys,
        "effective_cutoff_at": effective_cutoff_at,
        "refresh_nonce": refresh_nonce,
        "consumer_contract_version": consumer_contract_version,
    })

def operation_identity(
    *,
    request_identity: str,
    capability_key: str,
    provider_revision: str,
    provider_profile: str,
    transport_contract_hash: str,
    subject: Mapping[str, object],
    sanitized_parameters: Mapping[str, object],
) -> str:
    _validate_sha256(request_identity, "request_identity")
    _validate_exact_string(capability_key, "capability_key")
    _validate_exact_string(provider_revision, "provider_revision")
    _validate_exact_string(provider_profile, "provider_profile")
    _validate_sha256(transport_contract_hash, "transport_contract_hash")

    if not isinstance(subject, Mapping):
        raise TypeError("subject must be a Mapping")
    for k, v in subject.items():
        if type(k) is not str:
            raise TypeError("subject keys must be exact str")

    if not isinstance(sanitized_parameters, Mapping):
        raise TypeError("sanitized_parameters must be a Mapping")
    for k, v in sanitized_parameters.items():
        if type(k) is not str:
            raise TypeError("sanitized_parameters keys must be exact str")

    return canonical_sha256({
        "profile": "BET-OPERATION-1",
        "request_identity": request_identity,
        "capability_key": capability_key,
        "provider_revision": provider_revision,
        "provider_profile": provider_profile,
        "transport_contract_hash": transport_contract_hash,
        "subject": subject,
        "sanitized_parameters": sanitized_parameters,
    })

def attempt_identity(
    *,
    operation_identity: str,
    attempt_index: int,
) -> str:
    _validate_sha256(operation_identity, "operation_identity")
    if type(attempt_index) is not int or isinstance(attempt_index, bool) or attempt_index < 0:
        raise TypeError("attempt_index must be non-negative int")

    return canonical_sha256({
        "profile": "BET-ATTEMPT-1",
        "operation_identity": operation_identity,
        "attempt_index": attempt_index,
    })

def selection_epoch_identity(
    *,
    sport: str,
    capability_key: str,
    subject: Mapping[str, object],
    quality_profile: str,
    policy_tuple: Mapping[str, object],
    epoch: int,
) -> str:
    _validate_exact_string(sport, "sport")
    _validate_exact_string(capability_key, "capability_key")

    if not isinstance(subject, Mapping):
        raise TypeError("subject must be a Mapping")
    for k, v in subject.items():
        if type(k) is not str:
            raise TypeError("subject keys must be exact str")

    _validate_exact_string(quality_profile, "quality_profile")

    if not isinstance(policy_tuple, Mapping):
        raise TypeError("policy_tuple must be a Mapping")
    for k, v in policy_tuple.items():
        if type(k) is not str:
            raise TypeError("policy_tuple keys must be exact str")

    if type(epoch) is not int or isinstance(epoch, bool) or epoch < 0:
        raise TypeError("epoch must be non-negative int")

    return canonical_sha256({
        "profile": "BET-SELECTION-EPOCH-1",
        "sport": sport,
        "capability_key": capability_key,
        "subject": subject,
        "quality_profile": quality_profile,
        "policy_tuple": policy_tuple,
        "epoch": epoch,
    })
