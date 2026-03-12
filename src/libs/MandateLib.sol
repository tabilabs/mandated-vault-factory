// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC8192MandatedVault} from "../interfaces/IERC8192MandatedVault.sol";

/// @title MandateLib
/// @notice Pure validation logic for Mandate struct fields and input size limits.
/// @dev Extracted from MandatedVaultClone.execute() steps 1-5a and 10.
///      All functions are `internal` — inlined at compile time, zero extra gas.
///      Errors declared here (TooManyActions, ExtensionsTooLarge) are part of
///      MandatedVaultClone's public ABI — integrators should decode them alongside
///      IERC8192MandatedVault errors when handling execute() reverts.
library MandateLib {
    error TooManyActions(uint256 count);
    error ExtensionsTooLarge(uint256 length);

    /// @dev Validates mandate field constraints (spec steps 1-5a).
    /// @param mandate          The mandate to validate.
    /// @param currentEpoch     The vault's current authority epoch.
    /// @param actionsLen       Number of actions in the batch.
    /// @param adapterProofsLen Number of adapter proof arrays (must equal actionsLen).
    /// @param extensionsLen    Byte length of the encoded extensions blob.
    /// @param maxActions       Maximum allowed actions per execution.
    /// @param maxExtensionsBytes Maximum allowed extensions byte length.
    function validateFields(
        IERC8192MandatedVault.Mandate calldata mandate,
        uint64 currentEpoch,
        uint256 actionsLen,
        uint256 adapterProofsLen,
        uint256 extensionsLen,
        uint256 maxActions,
        uint256 maxExtensionsBytes
    ) internal view {
        // Step 1: deadline
        if (mandate.deadline != 0 && block.timestamp > mandate.deadline) {
            revert IERC8192MandatedVault.MandateExpired();
        }

        // Step 2: executor restriction
        if (mandate.executor != address(0) && msg.sender != mandate.executor) {
            revert IERC8192MandatedVault.UnauthorizedExecutor();
        }

        // Step 3: unbounded open mandate safety
        if (mandate.executor == address(0) && mandate.payloadDigest == bytes32(0)) {
            revert IERC8192MandatedVault.UnboundedOpenMandate();
        }

        // Step 4: authority epoch
        if (mandate.authorityEpoch != currentEpoch) {
            revert IERC8192MandatedVault.AuthorityEpochMismatch();
        }

        // Step 5: drawdown bounds
        if (mandate.maxDrawdownBps > 10_000) {
            revert IERC8192MandatedVault.InvalidDrawdownBps();
        }
        if (mandate.maxCumulativeDrawdownBps > 10_000 || mandate.maxCumulativeDrawdownBps < mandate.maxDrawdownBps) {
            revert IERC8192MandatedVault.InvalidCumulativeDrawdownBps();
        }
        if (mandate.allowedAdaptersRoot == bytes32(0)) {
            revert IERC8192MandatedVault.InvalidAdaptersRoot();
        }

        // Step 5a: input size limits (includes spec step 11: EmptyActions)
        if (actionsLen == 0) revert IERC8192MandatedVault.EmptyActions();
        if (actionsLen > maxActions) revert TooManyActions(actionsLen);
        if (adapterProofsLen != actionsLen) revert IERC8192MandatedVault.AdapterNotAllowed();
        if (extensionsLen > maxExtensionsBytes) revert ExtensionsTooLarge(extensionsLen);
    }

    /// @dev Validates optional payload binding (spec step 10).
    function validatePayloadDigest(bytes32 payloadDigest, bytes32 actionsDigest) internal pure {
        if (payloadDigest != bytes32(0) && payloadDigest != actionsDigest) {
            revert IERC8192MandatedVault.PayloadDigestMismatch();
        }
    }
}
