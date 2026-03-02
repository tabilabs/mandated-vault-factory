// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

// --- Upgradeable base contracts (ERC-7201 namespaced storage, Clone-safe) ----
import {ERC4626Upgradeable} from "@openzeppelin/contracts-upgradeable/token/ERC20/extensions/ERC4626Upgradeable.sol";
import {ERC165Upgradeable} from "@openzeppelin/contracts-upgradeable/utils/introspection/ERC165Upgradeable.sol";
import {EIP712Upgradeable} from "@openzeppelin/contracts-upgradeable/utils/cryptography/EIP712Upgradeable.sol";

// --- Standard (stateless) libraries & contracts ------------------------------
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC4626} from "@openzeppelin/contracts/interfaces/IERC4626.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

// --- Domain libraries -------------------------------------------------------
import {MandateLib} from "./libs/MandateLib.sol";
import {AdapterLib} from "./libs/AdapterLib.sol";
import {DrawdownLib} from "./libs/DrawdownLib.sol";

import {IERCXXXXMandatedVault} from "./interfaces/IERCXXXXMandatedVault.sol";

/// @title MandatedVaultClone
/// @notice ERC-1167 Clone-compatible implementation of the ERC-XXXX Mandated Execution vault.
/// @dev Adapted from the canonical MandatedVault reference implementation for the minimal
///      proxy (Clone) deployment pattern. Key differences from the reference:
///
///      1. Constructor logic replaced by `initialize()` + `_disableInitializers()`.
///      2. ERC4626 / ERC20 / EIP712 / ERC165 swapped to their Upgradeable variants
///         (ERC-7201 namespaced storage, no constructor dependencies).
///      3. ReentrancyGuard remains standard -- its storage slot starts at 0 in fresh
///         clones, which is safe because the entered check is `value == 2` (not `!= 1`).
///      4. Core validation logic delegated to domain libraries (MandateLib, AdapterLib,
///         DrawdownLib) for auditability and independent testability.
///
///      All core Mandated Execution semantics (17-step execute, circuit breaker,
///      Merkle adapter allowlist, EIP-712 signatures, nonce management) are identical
///      to the reference implementation.
contract MandatedVaultClone is
    ERC4626Upgradeable,
    ERC165Upgradeable,
    EIP712Upgradeable,
    ReentrancyGuard,
    IERCXXXXMandatedVault
{
    // --- Constants -----------------------------------------------------------

    /// @dev ERC-1271 magic value returned by valid contract signatures.
    bytes4 internal constant _ERC1271_MAGICVALUE = 0x1626ba7e;

    /// @dev Extension identifier for the selector allowlist extension.
    ///      "erc-xxxx" is the draft ERC number placeholder; it will be replaced with the assigned
    ///      number once the EIP editor assigns one. This constant is intentionally frozen as-is
    ///      for the draft phase. Deployed vaults will retain the draft identifier.
    bytes4 internal constant _SELECTOR_ALLOWLIST_ID = bytes4(keccak256("erc-xxxx:selector-allowlist@v1"));

    /// @dev EIP-712 typehash for the Mandate struct.
    bytes32 internal constant _MANDATE_TYPEHASH = keccak256(
        "Mandate(address executor,uint256 nonce,uint48 deadline,uint64 authorityEpoch,"
        "uint16 maxDrawdownBps,uint16 maxCumulativeDrawdownBps,bytes32 allowedAdaptersRoot,"
        "bytes32 payloadDigest,bytes32 extensionsHash)"
    );

    /// @notice Maximum number of actions per execution (DoS mitigation).
    uint256 public constant MAX_ACTIONS = 32;

    /// @notice Maximum number of extensions per execution.
    uint256 public constant MAX_EXTENSIONS = 16;

    /// @notice Maximum Merkle proof depth for adapter allowlist verification.
    uint256 public constant MAX_ADAPTER_PROOF_DEPTH = 64;

    /// @notice Maximum Merkle proof depth for selector allowlist verification.
    uint256 public constant MAX_SELECTOR_PROOF_DEPTH = 64;

    /// @notice Maximum byte length of the encoded extensions blob (128 KiB).
    uint256 public constant MAX_EXTENSIONS_BYTES = 131_072;

    /// @notice Maximum return data bytes copied on action failure (4 KiB, gas griefing mitigation).
    uint256 public constant MAX_RETURNDATA_BYTES = 4096;

    // --- Implementation-specific events & errors -----------------------------

    /// @notice Emitted when native ETH is swept from the vault by the authority.
    event NativeSwept(address indexed to, uint256 amount);

    error NativeSweepFailed();
    error ZeroAddressRecipient();
    error ZeroAddressAsset();
    error TooManyExtensions(uint256 count);

    // --- State variables -----------------------------------------------------
    // Stored in sequential slots starting at 0. No collision risk with OZ's
    // ERC-7201 namespaced storage (hash-derived slots in the upper address space).

    address private _authority;
    address private _pendingAuthority;
    uint64 private _authorityEpoch;

    mapping(address => mapping(uint256 => bool)) private _nonceUsed;
    mapping(address => uint256) private _nonceThreshold;
    mapping(bytes32 => bool) private _mandateRevoked;

    uint48 private _epochStart;
    uint256 private _epochAssets;

    // --- Constructor & Initializer -------------------------------------------

    /// @dev Locks the implementation contract, preventing direct initialization.
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Initializes a freshly-cloned vault instance.
    /// @dev Called exactly once by the VaultFactory immediately after
    ///      `Clones.cloneDeterministic`. Init order: ERC20 -> ERC4626 -> EIP712 -> ERC165.
    /// @param asset_      The underlying ERC-20 asset token.
    /// @param name_       The ERC-20 name for vault shares.
    /// @param symbol_     The ERC-20 symbol for vault shares.
    /// @param authority_  The initial mandate authority (signer).
    function initialize(IERC20 asset_, string calldata name_, string calldata symbol_, address authority_)
        external
        initializer
    {
        if (authority_ == address(0)) revert ZeroAddressAuthority();
        if (address(asset_) == address(0)) revert ZeroAddressAsset();

        __ERC20_init(name_, symbol_);
        __ERC4626_init(asset_);
        __EIP712_init("MandatedExecution", "1");
        __ERC165_init();

        _authority = authority_;
    }

    // --- Views ---------------------------------------------------------------

    /// @inheritdoc IERCXXXXMandatedVault
    function mandateAuthority() public view returns (address) {
        return _authority;
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function authorityEpoch() external view returns (uint64) {
        return _authorityEpoch;
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function pendingAuthority() external view returns (address) {
        return _pendingAuthority;
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function isNonceUsed(address authority, uint256 nonce) external view returns (bool) {
        return _nonceUsed[authority][nonce];
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function nonceThreshold(address authority) external view returns (uint256) {
        return _nonceThreshold[authority];
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function isMandateRevoked(bytes32 mandateHash) external view returns (bool) {
        return _mandateRevoked[mandateHash];
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function epochStart() external view returns (uint48) {
        return _epochStart;
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function epochAssets() external view returns (uint256) {
        return _epochAssets;
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function supportsExtension(bytes4 id) public view returns (bool) {
        return _supportsExtension(id);
    }

    /// @dev Reports ERC-165 interface support for IERCXXXXMandatedVault and IERC4626.
    function supportsInterface(bytes4 interfaceId) public view override returns (bool) {
        return interfaceId == type(IERCXXXXMandatedVault).interfaceId || interfaceId == type(IERC4626).interfaceId
            || super.supportsInterface(interfaceId);
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function hashActions(Action[] calldata actions) external pure returns (bytes32) {
        return keccak256(abi.encode(actions));
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function hashMandate(Mandate calldata mandate) public view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(
                _MANDATE_TYPEHASH,
                mandate.executor,
                mandate.nonce,
                mandate.deadline,
                mandate.authorityEpoch,
                mandate.maxDrawdownBps,
                mandate.maxCumulativeDrawdownBps,
                mandate.allowedAdaptersRoot,
                mandate.payloadDigest,
                mandate.extensionsHash
            )
        );
        return _hashTypedDataV4(structHash);
    }

    // --- Authority management (2-step transfer) ------------------------------

    /// @inheritdoc IERCXXXXMandatedVault
    function proposeAuthority(address newAuthority) external {
        if (msg.sender != _authority) revert NotAuthority();
        _pendingAuthority = newAuthority;
        emit AuthorityProposed(_authority, newAuthority);
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function acceptAuthority() external {
        if (msg.sender != _pendingAuthority) revert NotAuthority();
        address prev = _authority;
        _authority = _pendingAuthority;
        _pendingAuthority = address(0);
        unchecked {
            _authorityEpoch++;
        }
        emit AuthorityTransferred(prev, _authority);
    }

    // --- Epoch management ----------------------------------------------------

    /// @inheritdoc IERCXXXXMandatedVault
    function resetEpoch() external {
        if (msg.sender != _authority) revert NotAuthority();
        _epochAssets = totalAssets();
        _epochStart = uint48(block.timestamp);
        emit EpochReset(_authority, _epochAssets, _epochStart);
    }

    // --- Revocation ----------------------------------------------------------

    /// @inheritdoc IERCXXXXMandatedVault
    function invalidateNonce(uint256 nonce) external {
        if (msg.sender != _authority) revert NotAuthority();
        _nonceUsed[_authority][nonce] = true;
        emit NonceInvalidated(_authority, nonce);
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function invalidateNoncesBelow(uint256 threshold) external {
        if (msg.sender != _authority) revert NotAuthority();
        if (threshold <= _nonceThreshold[_authority]) revert ThresholdNotIncreased();
        _nonceThreshold[_authority] = threshold;
        emit NoncesInvalidatedBelow(_authority, threshold);
    }

    /// @inheritdoc IERCXXXXMandatedVault
    function revokeMandate(bytes32 mandateHash) external {
        if (msg.sender != _authority) revert NotAuthority();
        _mandateRevoked[mandateHash] = true;
        emit MandateRevoked(mandateHash, _authority);
    }

    // --- Execution -----------------------------------------------------------

    /// @inheritdoc IERCXXXXMandatedVault
    function execute(
        Mandate calldata mandate,
        Action[] calldata actions,
        bytes calldata signature,
        bytes32[][] calldata adapterProofs,
        bytes calldata extensions
    ) external nonReentrant returns (uint256 preAssets, uint256 postAssets) {
        // -- Steps 1-12a: Validation (caches authority + hashes for reuse) ----
        (address authority_, bytes32 mandateHash_, bytes32 actionsDigest_) =
            _validateMandate(mandate, actions, signature, adapterProofs, extensions);

        // -- Step 13: Pre-state snapshot & epoch initialization ----------------
        preAssets = totalAssets();
        if (_epochStart == 0) {
            _epochStart = uint48(block.timestamp);
            _epochAssets = preAssets;
        }

        // -- Step 14: Execute actions -----------------------------------------
        _executeActions(actions);

        // -- Step 15-17: Post-state, circuit breaker & event ------------------
        postAssets = _postExecution(mandate, preAssets, authority_, mandateHash_, actionsDigest_);
    }

    /// @dev Validates mandate fields, signature, nonce, and payload binding
    ///      (steps 1-10). Factored out from `execute()` for stack depth.
    /// @return authority_    The authority at validation time (cached before action execution
    ///                       to avoid reading a potentially stale `_authority` post-execution).
    /// @return mandateHash_  The EIP-712 mandate hash (cached to avoid recomputation in event).
    /// @return actionsDigest_ The keccak256 of encoded actions (cached for event emission and
    ///                        optional payloadDigest binding validation).
    function _validateMandate(
        Mandate calldata mandate,
        Action[] calldata actions,
        bytes calldata signature,
        bytes32[][] calldata adapterProofs,
        bytes calldata extensions
    ) internal returns (address authority_, bytes32 mandateHash_, bytes32 actionsDigest_) {
        // -- Steps 1-5a: Mandate field validation -----------------------------
        MandateLib.validateFields(
            mandate,
            _authorityEpoch,
            actions.length,
            adapterProofs.length,
            extensions.length,
            MAX_ACTIONS,
            MAX_EXTENSIONS_BYTES
        );

        // -- Step 6: Extensions hash ------------------------------------------
        if (keccak256(extensions) != mandate.extensionsHash) revert ExtensionsHashMismatch();

        // -- Step 7: Mandate hash & revocation --------------------------------
        mandateHash_ = hashMandate(mandate);
        if (_mandateRevoked[mandateHash_]) revert MandateIsRevoked();

        // -- Step 8: Signature verification (cache authority before actions) ---
        authority_ = _authority;
        _verifyAuthoritySig(authority_, mandateHash_, signature);

        // -- Step 9: Nonce replay protection ----------------------------------
        _consumeNonce(authority_, mandate.nonce);

        // -- Step 10: Payload binding -----------------------------------------
        // Compute actionsDigest once: it is always required for the MandateExecuted event,
        // and it is also used for optional payloadDigest binding validation.
        actionsDigest_ = keccak256(abi.encode(actions));
        MandateLib.validatePayloadDigest(mandate.payloadDigest, actionsDigest_);

        // -- Steps 12-12a: Adapter & selector allowlists ----------------------
        _validateAllowlists(mandate, actions, adapterProofs, extensions);
    }

    /// @dev Validates adapter Merkle proofs and optional selector allowlist
    ///      (steps 12 + 12a). Factored out from `_validateMandate` to keep
    ///      each function within legacy codegen's 16-slot stack limit.
    function _validateAllowlists(
        Mandate calldata mandate,
        Action[] calldata actions,
        bytes32[][] calldata adapterProofs,
        bytes calldata extensions
    ) internal view {
        // -- Step 12: Adapter allowlist ---------------------------------------
        AdapterLib.validateAdapters(actions, adapterProofs, mandate.allowedAdaptersRoot, MAX_ADAPTER_PROOF_DEPTH);

        // -- Step 12a: Selector allowlist (from extensions) -------------------
        if (extensions.length != 0) {
            (bool hasSelectorAllowlist, bytes32 selectorRoot, bytes32[][] memory selectorProofs) =
                _parseExtensions(extensions);
            if (hasSelectorAllowlist) {
                AdapterLib.enforceSelectorAllowlist(actions, selectorRoot, selectorProofs, MAX_SELECTOR_PROOF_DEPTH);
            }
        }
    }

    /// @dev Executes all actions via delegated calls (step 14).
    function _executeActions(Action[] calldata actions) internal {
        uint256 len = actions.length;
        for (uint256 i = 0; i < len;) {
            (bool ok,) = actions[i].adapter.call{value: actions[i].value}(actions[i].data);
            if (!ok) revert ActionCallFailed(i, _copyReturnData());
            unchecked {
                ++i;
            }
        }
    }

    /// @dev Consumes nonce for the given authority (step 9).
    ///      Accepts the cached authority to avoid re-reading `_authority` from storage,
    ///      ensuring semantic consistency if future changes introduce external calls
    ///      between step 8 and step 9.
    function _consumeNonce(address authority_, uint256 nonce) internal {
        if (nonce < _nonceThreshold[authority_]) revert NonceBelowThreshold();
        if (_nonceUsed[authority_][nonce]) revert NonceAlreadyUsed();
        _nonceUsed[authority_][nonce] = true;
    }

    /// @dev Post-execution: drawdown checks + event emission (steps 15-17).
    ///      Factored out from `execute()` to keep stack depth within legacy codegen limits.
    ///      Uses cached mandateHash_ and actionsDigest_ to avoid redundant keccak256 calls.
    function _postExecution(
        Mandate calldata mandate,
        uint256 preAssets,
        address authority_,
        bytes32 mandateHash_,
        bytes32 actionsDigest_
    ) internal returns (uint256 postAssets) {
        postAssets = totalAssets();
        DrawdownLib.checkSingleDrawdown(preAssets, postAssets, mandate.maxDrawdownBps);
        _epochAssets = DrawdownLib.checkCumulativeDrawdown(_epochAssets, postAssets, mandate.maxCumulativeDrawdownBps);
        emit MandateExecuted(mandateHash_, authority_, msg.sender, actionsDigest_, preAssets, postAssets);
    }

    // --- Internal helpers ----------------------------------------------------

    /// @dev Returns true if the given extension ID is supported by this vault.
    function _supportsExtension(bytes4 id) internal view virtual returns (bool) {
        return id == _SELECTOR_ALLOWLIST_ID;
    }

    /// @dev Parses and validates the extensions blob. Uses try/catch for safe ABI decoding.
    /// @return hasSelectorAllowlist Whether the selector allowlist extension is present.
    /// @return selectorRoot        The Merkle root for selector allowlist (if present).
    /// @return selectorProofs      The per-action Merkle proofs for selector allowlist (if present).
    function _parseExtensions(bytes calldata extensions)
        internal
        view
        returns (bool hasSelectorAllowlist, bytes32 selectorRoot, bytes32[][] memory selectorProofs)
    {
        try this.decodeExtensions(extensions) returns (Extension[] memory exts) {
            if (exts.length > MAX_EXTENSIONS) revert TooManyExtensions(exts.length);
            for (uint256 i = 1; i < exts.length;) {
                if (exts[i - 1].id >= exts[i].id) {
                    revert ExtensionsNotCanonical();
                }
                unchecked {
                    ++i;
                }
            }
            for (uint256 i = 0; i < exts.length;) {
                if (exts[i].required && !_supportsExtension(exts[i].id)) {
                    revert UnsupportedRequiredExtension(exts[i].id);
                }
                if (exts[i].id == _SELECTOR_ALLOWLIST_ID) {
                    hasSelectorAllowlist = true;
                    try this.decodeSelectorAllowlist(exts[i].data) returns (bytes32 root, bytes32[][] memory proofs) {
                        selectorRoot = root;
                        selectorProofs = proofs;
                    } catch {
                        revert InvalidExtensionsEncoding();
                    }
                }
                unchecked {
                    ++i;
                }
            }
        } catch {
            revert InvalidExtensionsEncoding();
        }
    }

    /// @notice Decodes an ABI-encoded Extension[] blob. External for try/catch usage.
    /// @param extensions The ABI-encoded Extension array.
    /// @return The decoded Extension array.
    function decodeExtensions(bytes calldata extensions) external pure returns (Extension[] memory) {
        return abi.decode(extensions, (Extension[]));
    }

    /// @notice Decodes ABI-encoded selector allowlist extension data. External for try/catch usage.
    /// @param data The ABI-encoded (bytes32 root, bytes32[][] proofs) blob.
    /// @return root The Merkle root of the selector allowlist.
    /// @return proofs The per-action selector Merkle proofs.
    function decodeSelectorAllowlist(bytes calldata data)
        external
        pure
        returns (bytes32 root, bytes32[][] memory proofs)
    {
        (root, proofs) = abi.decode(data, (bytes32, bytes32[][]));
    }

    /// @dev Copies return data from the last external call into a `bytes memory`.
    ///      Capped at MAX_RETURNDATA_BYTES to prevent gas griefing via oversized return data.
    function _copyReturnData() internal pure returns (bytes memory ret) {
        assembly ("memory-safe") {
            let size := returndatasize()
            // Cap to prevent gas griefing from malicious large return data
            if gt(size, MAX_RETURNDATA_BYTES) { size := MAX_RETURNDATA_BYTES }
            ret := mload(0x40)
            mstore(ret, size)
            let dst := add(ret, 0x20)
            returndatacopy(dst, 0, size)
            mstore(0x40, add(dst, and(add(size, 0x1f), not(0x1f))))
        }
    }

    /// @dev Verifies the authority's signature over a mandate hash.
    ///      Supports both EOA (ECDSA) and smart contract (ERC-1271) authorities.
    function _verifyAuthoritySig(address authority_, bytes32 digest, bytes calldata signature) internal view {
        if (authority_.code.length == 0) {
            // EOA path: ECDSA recovery
            (address signer, ECDSA.RecoverError err,) = ECDSA.tryRecoverCalldata(digest, signature);
            if (err != ECDSA.RecoverError.NoError || signer != authority_) revert InvalidSignature();
            return;
        }

        // Smart contract path: ERC-1271 validation
        bytes4 magic = _ERC1271_MAGICVALUE;
        uint256 length = signature.length;
        bool ok;

        assembly ("memory-safe") {
            let ptr := mload(0x40)
            // `bytes4` values are left-aligned in the 32-byte word, so this writes the selector
            // into the first 4 bytes of calldata. Do not refactor `magic` to a uint32 without
            // also applying a 224-bit shift.
            mstore(ptr, magic)
            mstore(add(ptr, 0x04), digest)
            mstore(add(ptr, 0x24), 0x40)
            mstore(add(ptr, 0x44), length)
            calldatacopy(add(ptr, 0x64), signature.offset, length)

            ok := staticcall(gas(), authority_, ptr, add(length, 0x64), 0x00, 0x20)
            ok := and(ok, and(gt(returndatasize(), 0x1f), eq(mload(0x00), magic)))
        }

        if (!ok) revert InvalidSignature();
    }

    // --- ERC-4626 overrides (VaultBusy guard) --------------------------------
    // Prevent deposits/withdrawals while an `execute()` is in progress.

    /// @dev Allows the vault to receive native ETH (e.g., from adapter calls).
    receive() external payable {}

    /// @inheritdoc ERC4626Upgradeable
    function deposit(uint256 assets, address receiver) public override returns (uint256) {
        if (_reentrancyGuardEntered()) revert VaultBusy();
        return super.deposit(assets, receiver);
    }

    /// @inheritdoc ERC4626Upgradeable
    function mint(uint256 shares, address receiver) public override returns (uint256) {
        if (_reentrancyGuardEntered()) revert VaultBusy();
        return super.mint(shares, receiver);
    }

    /// @inheritdoc ERC4626Upgradeable
    function withdraw(uint256 assets, address receiver, address owner) public override returns (uint256) {
        if (_reentrancyGuardEntered()) revert VaultBusy();
        return super.withdraw(assets, receiver, owner);
    }

    /// @inheritdoc ERC4626Upgradeable
    function redeem(uint256 shares, address receiver, address owner) public override returns (uint256) {
        if (_reentrancyGuardEntered()) revert VaultBusy();
        return super.redeem(shares, receiver, owner);
    }

    // --- Authority escape hatch ----------------------------------------------

    /// @notice Authority-only escape hatch for native ETH accidentally or forcibly sent to the vault.
    /// @param to     The recipient address.
    /// @param amount The amount of native ETH to sweep.
    function sweepNative(address payable to, uint256 amount) external {
        if (msg.sender != _authority) revert NotAuthority();
        if (to == address(0)) revert ZeroAddressRecipient();
        emit NativeSwept(to, amount);
        (bool ok,) = to.call{value: amount}("");
        if (!ok) revert NativeSweepFailed();
    }
}
