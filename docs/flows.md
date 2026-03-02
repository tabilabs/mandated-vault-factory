# Mandated Vault Factory Flows

This document captures key runtime flows and contributor-facing execution paths.

## 1. Deterministic Vault Creation Flow (`createVault`)

```mermaid
sequenceDiagram
    autonumber
    participant C as Creator
    participant F as VaultFactory
    participant OZ as Clones (OZ)
    participant V as MandatedVaultClone (new clone)

    C->>F: createVault(asset, name, symbol, authority, salt)
    F->>F: actualSalt = keccak256(creator, asset, name, symbol, authority, salt)
    F->>OZ: cloneDeterministic(implementation, actualSalt)
    OZ-->>F: vault address
    F->>V: initialize(asset, name, symbol, authority)
    F->>F: register _isVault + _vaultsByCreator + _vaultCount
    F-->>C: emit VaultCreated
```

## 2. Address Prediction Flow (`predictVaultAddress`)

```mermaid
flowchart TD
    A[Input params] --> B{Which overload?}
    B -->|without creator| C[creator = msg.sender]
    B -->|with creator| D[use explicit creator]
    C --> E[actualSalt = keccak256(creator, asset, name, symbol, authority, salt)]
    D --> E
    E --> F[Clones.predictDeterministicAddress]
    F --> G[predicted vault address]
```

## 3. Mandate Execution Main Flow (`execute`)

```mermaid
flowchart TD
    S[Start execute] --> V1[Validate mandate fields\nstep 1-5a]
    V1 --> V2{extensions hash matches?}
    V2 -->|No| R1[Revert ExtensionsHashMismatch]
    V2 -->|Yes| V3[Decode extensions\nselector allowlist optional]

    V3 --> V4{mandate revoked?}
    V4 -->|Yes| R2[Revert MandateIsRevoked]
    V4 -->|No| V5[Verify signature\nEOA or ERC-1271]

    V5 --> V6{nonce valid and unused?}
    V6 -->|No| R3[Revert NonceBelowThreshold/NonceAlreadyUsed]
    V6 -->|Yes| V7[Mark nonce used]

    V7 --> V8{payloadDigest valid?}
    V8 -->|No| R4[Revert PayloadDigestMismatch]
    V8 -->|Yes| V9[Validate adapter merkle proofs]

    V9 --> V10{selector allowlist active?}
    V10 -->|Yes| V11[Validate selector proofs]
    V10 -->|No| V12[Skip selector check]
    V11 --> V13[Take preAssets snapshot]
    V12 --> V13

    V13 --> V14[Execute actions loop\nadapter.call]
    V14 --> V15[Take postAssets snapshot]
    V15 --> V16[Check single + cumulative drawdown]
    V16 --> V17[Emit MandateExecuted]
    V17 --> E[Return preAssets, postAssets]
```

## 4. Authority Lifecycle Flow

```mermaid
stateDiagram-v2
    [*] --> ActiveAuthority
    ActiveAuthority --> ProposedAuthority: proposeAuthority(newAuthority)
    ProposedAuthority --> ActiveAuthority: acceptAuthority() by pendingAuthority
    ActiveAuthority --> ActiveAuthority: invalidateNonce / invalidateNoncesBelow
    ActiveAuthority --> ActiveAuthority: revokeMandate
    ActiveAuthority --> ActiveAuthority: resetEpoch
```

## 5. Drawdown Protection Flow

```mermaid
flowchart LR
    A[preAssets] --> B[execute actions]
    B --> C[postAssets]
    C --> D[checkSingleDrawdown]
    D --> E[checkCumulativeDrawdown]
    E --> F[update epoch high-water mark]
```

## 6. Failure Surface Map

- **Authorization/identity**: `NotAuthority`, `UnauthorizedExecutor`, `InvalidSignature`.
- **Replay/revocation**: `NonceAlreadyUsed`, `NonceBelowThreshold`, `MandateIsRevoked`.
- **Payload/extension integrity**: `PayloadDigestMismatch`, `ExtensionsHashMismatch`, `InvalidExtensionsEncoding`, `ExtensionsNotCanonical`.
- **Adapter controls**: `AdapterNotAllowed`, `SelectorNotAllowed`, `InvalidActionData`, proof depth errors.
- **Risk controls**: `DrawdownExceeded`, `CumulativeDrawdownExceeded`.
