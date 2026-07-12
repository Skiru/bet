# Model Inheritance Policy

The active model selected in the Kilo UI/parent session is the runtime source of truth. Every production betting agent inherits it and must not define a per-agent provider/model override.

Runtime certification launches `bet-executor` without `--model`, checks for `ProviderModelNotFoundError` and silent fallback, and records resolved model/provider metadata only when the CLI exposes it. Changing a local serving profile remains an engineering operation requiring benchmark and rollback evidence; it does not authorize an agent model pin.
