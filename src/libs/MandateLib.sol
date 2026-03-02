// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERCXXXXMandatedVault} from "../interfaces/IERCXXXXMandatedVault.sol";

/// @title MandateLib
/// @notice Pure validation logic for Mandate struct fields and input size limits.
/// @dev Extracted from MandatedVaultClone.execute() steps 1-5a and 10.
///      All functions are `internal` — inlined at compile time, zero extra gas.
///      Errors declared here (TooManyActions, ExtensionsTooLarge) are part of
///      MandatedVaultClone's public ABI — integrators should decode them alongside
///      IERCXXXXMandatedVault errors when handling execute() reverts.
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
        IERCXXXXMandatedVault.Mandate calldata mandate,
        uint64 currentEpoch,
        uint256 actionsLen,
        uint256 adapterProofsLen,
        uint256 extensionsLen,
        uint256 maxActions,
        uint256 maxExtensionsBytes
    ) internal view {
        // Step 1: deadline
        if (mandate.deadline != 0 && block.timestamp > mandate.deadline) {
            revert IERCXXXXMandatedVault.MandateExpired();
        }

        // Step 2: executor restriction
        if (mandate.executor != address(0) && msg.sender != mandate.executor) {
            revert IERCXXXXMandatedVault.UnauthorizedExecutor();
        }

        // Step 3: unbounded open mandate safety
        if (mandate.executor == address(0) && mandate.payloadDigest == bytes32(0)) {
            revert IERCXXXXMandatedVault.UnboundedOpenMandate();
        }

        // Step 4: authority epoch
        if (mandate.authorityEpoch != currentEpoch) {
            revert IERCXXXXMandatedVault.AuthorityEpochMismatch();
        }

        // Step 5: drawdown bounds
        if (mandate.maxDrawdownBps > 10_000) {
            revert IERCXXXXMandatedVault.InvalidDrawdownBps();
        }
        if (mandate.maxCumulativeDrawdownBps > 10_000 || mandate.maxCumulativeDrawdownBps < mandate.maxDrawdownBps) {
            revert IERCXXXXMandatedVault.InvalidCumulativeDrawdownBps();
        }
        if (mandate.allowedAdaptersRoot == bytes32(0)) {
            revert IERCXXXXMandatedVault.InvalidAdaptersRoot();
        }

        // Step 5a: input size limits (includes spec step 11: EmptyActions)
        if (actionsLen == 0) revert IERCXXXXMandatedVault.EmptyActions();
        if (actionsLen > maxActions) revert TooManyActions(actionsLen);
        if (adapterProofsLen != actionsLen) revert IERCXXXXMandatedVault.AdapterNotAllowed();
        if (extensionsLen > maxExtensionsBytes) revert ExtensionsTooLarge(extensionsLen);
    }

    /// @dev Validates optional payload binding (spec step 10).
    function validatePayloadDigest(bytes32 payloadDigest, bytes32 actionsDigest) internal pure {
        if (payloadDigest != bytes32(0) && payloadDigest != actionsDigest) {
            revert IERCXXXXMandatedVault.PayloadDigestMismatch();
        }
    }
}
