// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/// @title IERC8192MandatedVault
/// @notice Minimal interface for risk-constrained delegated strategy execution on ERC-4626 vaults.
/// @dev ERC-8192-compliant vaults MUST also implement IERC4626 and IERC165.
interface IERC8192MandatedVault {
    /* is IERC4626, IERC165 */
    // --------- Structs ---------

    struct Action {
        address adapter;
        uint256 value;
        bytes data;
    }

    struct Mandate {
        address executor;
        uint256 nonce;
        uint48 deadline;
        uint64 authorityEpoch;
        uint16 maxDrawdownBps;
        uint16 maxCumulativeDrawdownBps;
        bytes32 allowedAdaptersRoot;
        bytes32 payloadDigest;
        bytes32 extensionsHash;
    }

    struct Extension {
        bytes4 id;
        bool required;
        bytes data;
    }

    // --------- Events ---------

    /// @notice Emitted when a mandate is successfully executed.
    event MandateExecuted(
        bytes32 indexed mandateHash,
        address indexed authority,
        address indexed executor,
        bytes32 actionsDigest,
        uint256 preAssets,
        uint256 postAssets
    );

    /// @notice Emitted when a mandate is revoked by the authority.
    event MandateRevoked(bytes32 indexed mandateHash, address indexed authority);
    /// @notice Emitted when a specific nonce is invalidated.
    event NonceInvalidated(address indexed authority, uint256 indexed nonce);
    /// @notice Emitted when all nonces below a threshold are invalidated.
    event NoncesInvalidatedBelow(address indexed authority, uint256 threshold);
    /// @notice Emitted when authority is transferred (2-step complete).
    event AuthorityTransferred(address indexed previousAuthority, address indexed newAuthority);
    /// @notice Emitted when a new authority is proposed (2-step initiate).
    event AuthorityProposed(address indexed currentAuthority, address indexed proposedAuthority);
    /// @notice Emitted when the epoch is reset (e.g., after authority transfer).
    event EpochReset(address indexed authority, uint256 newEpochAssets, uint48 newEpochStart);

    // --------- Errors ---------

    error NotAuthority();
    error UnauthorizedExecutor();
    error MandateExpired();
    error AuthorityEpochMismatch();
    error InvalidSignature();
    error NonceAlreadyUsed();
    error NonceBelowThreshold();
    error ThresholdNotIncreased();
    error MandateIsRevoked();
    error ExtensionsHashMismatch();
    error PayloadDigestMismatch();
    error AdapterNotAllowed();
    error UnsupportedRequiredExtension(bytes4 id);
    error InvalidDrawdownBps();
    error InvalidCumulativeDrawdownBps();
    error InvalidAdaptersRoot();
    error DrawdownExceeded();
    error CumulativeDrawdownExceeded();
    error AbsoluteLossExceeded();
    error UnboundedOpenMandate();
    error EmptyActions();
    error NonZeroActionValue();
    error ActionCallFailed(uint256 index, bytes reason);
    error ZeroAddressAuthority();
    error InvalidExtensionsEncoding();
    error ExtensionsNotCanonical();
    error VaultBusy();

    // --------- Views ---------

    /// @notice Returns the current authority address.
    function mandateAuthority() external view returns (address);
    /// @notice Returns the current authority epoch counter.
    function authorityEpoch() external view returns (uint64);
    /// @notice Returns whether a nonce has been used by the given authority.
    function isNonceUsed(address authority, uint256 nonce) external view returns (bool);
    /// @notice Returns whether a mandate hash has been revoked.
    function isMandateRevoked(bytes32 mandateHash) external view returns (bool);
    /// @notice Returns the nonce threshold for the given authority.
    function nonceThreshold(address authority) external view returns (uint256);
    /// @notice Returns the EIP-712 hash of a mandate struct.
    function hashMandate(Mandate calldata mandate) external view returns (bytes32);
    /// @notice Returns the keccak256 digest of an actions array.
    function hashActions(Action[] calldata actions) external pure returns (bytes32);
    /// @notice Returns the timestamp when the current epoch started.
    function epochStart() external view returns (uint48);
    /// @notice Returns the totalAssets snapshot at epoch start (high-water mark).
    function epochAssets() external view returns (uint256);
    /// @notice Returns whether a given extension ID is supported.
    function supportsExtension(bytes4 id) external view returns (bool);

    // --------- Authority management ---------

    /// @notice Returns the pending authority address (0 if none proposed).
    function pendingAuthority() external view returns (address);
    /// @notice Proposes a new authority (step 1 of 2-step transfer).
    /// @param newAuthority The address of the proposed new authority.
    function proposeAuthority(address newAuthority) external;
    /// @notice Accepts authority transfer (step 2, called by the proposed authority).
    function acceptAuthority() external;

    // --------- Epoch management ---------

    /// @notice Resets the epoch, snapshotting current totalAssets as the new high-water mark.
    function resetEpoch() external;

    // --------- Revocation ---------

    /// @notice Revokes a specific mandate by its hash.
    /// @param mandateHash The EIP-712 hash of the mandate to revoke.
    function revokeMandate(bytes32 mandateHash) external;
    /// @notice Invalidates a specific nonce.
    /// @param nonce The nonce to invalidate.
    function invalidateNonce(uint256 nonce) external;
    /// @notice Invalidates all nonces below the given threshold.
    /// @param threshold The new minimum nonce value (must be greater than current).
    function invalidateNoncesBelow(uint256 threshold) external;

    // --------- Execution ---------

    /// @notice Executes a signed mandate: validates signature, enforces constraints, runs actions.
    /// @param mandate The signed mandate struct containing execution constraints.
    /// @param actions The ordered list of adapter calls to execute.
    /// @param signature The authority's EIP-712 signature (ECDSA or ERC-1271).
    /// @param adapterProofs Merkle proofs for each action's adapter in the allowlist.
    /// @param extensions ABI-encoded Extension[] for optional constraint modules.
    /// @return preAssets totalAssets before execution.
    /// @return postAssets totalAssets after execution.
    function execute(
        Mandate calldata mandate,
        Action[] calldata actions,
        bytes calldata signature,
        bytes32[][] calldata adapterProofs,
        bytes calldata extensions
    ) external returns (uint256 preAssets, uint256 postAssets);
}
