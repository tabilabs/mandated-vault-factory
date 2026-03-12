// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {IERC8192MandatedVault} from "../interfaces/IERC8192MandatedVault.sol";

/// @title AdapterLib
/// @notice Adapter allowlist and selector allowlist Merkle proof verification.
/// @dev Extracted from MandatedVaultClone.execute() steps 12 and 12a.
///      Errors declared here (AdapterProofTooDeep, InvalidActionData,
///      SelectorNotAllowed, SelectorProofTooDeep) are part of MandatedVaultClone's
///      public ABI — integrators should decode them alongside IERC8192MandatedVault
///      errors when handling execute() reverts.
library AdapterLib {
    /// @dev Codehash of an empty account (no deployed code).
    bytes32 internal constant EMPTY_CODEHASH = keccak256("");

    error AdapterProofTooDeep(uint256 index, uint256 depth);
    error InvalidActionData(uint256 index);
    error SelectorNotAllowed(uint256 index, address adapter, bytes4 selector);
    error SelectorProofTooDeep(uint256 index, uint256 depth);

    /// @dev Validates each action's adapter against the Merkle allowlist (spec step 12).
    /// @param actions           The actions to validate.
    /// @param adapterProofs     Per-action Merkle proofs for the adapter allowlist.
    /// @param allowedAdaptersRoot The Merkle root of allowed (adapter, codehash) pairs.
    /// @param maxProofDepth     Maximum allowed proof depth (DoS mitigation).
    function validateAdapters(
        IERC8192MandatedVault.Action[] calldata actions,
        bytes32[][] calldata adapterProofs,
        bytes32 allowedAdaptersRoot,
        uint256 maxProofDepth
    ) internal view {
        uint256 len = actions.length;
        for (uint256 i = 0; i < len;) {
            address adapter = actions[i].adapter;
            bytes32 codeHash = adapter.codehash;

            // Reject EOAs / precompiles / non-existent accounts
            if (codeHash == bytes32(0) || codeHash == EMPTY_CODEHASH) {
                revert IERC8192MandatedVault.AdapterNotAllowed();
            }
            if (actions[i].value != 0) revert IERC8192MandatedVault.NonZeroActionValue();
            if (adapterProofs[i].length > maxProofDepth) {
                revert AdapterProofTooDeep(i, adapterProofs[i].length);
            }

            bytes32 leaf = keccak256(abi.encode(adapter, codeHash));
            if (!MerkleProof.verifyCalldata(adapterProofs[i], allowedAdaptersRoot, leaf)) {
                revert IERC8192MandatedVault.AdapterNotAllowed();
            }
            unchecked {
                ++i;
            }
        }
    }

    /// @dev Enforces the selector allowlist for each action using Merkle proofs (spec step 12a).
    /// @param actions       The actions to validate selectors for.
    /// @param root          The Merkle root of allowed (adapter, selector) pairs.
    /// @param proofs        Per-action Merkle proofs for the selector allowlist.
    /// @param maxProofDepth Maximum allowed proof depth.
    function enforceSelectorAllowlist(
        IERC8192MandatedVault.Action[] calldata actions,
        bytes32 root,
        bytes32[][] memory proofs,
        uint256 maxProofDepth
    ) internal pure {
        if (proofs.length != actions.length) {
            revert IERC8192MandatedVault.InvalidExtensionsEncoding();
        }
        for (uint256 i = 0; i < actions.length;) {
            if (proofs[i].length > maxProofDepth) {
                revert SelectorProofTooDeep(i, proofs[i].length);
            }
            bytes calldata callData = actions[i].data;
            if (callData.length < 4) revert InvalidActionData(i);
            bytes4 selector;
            assembly ("memory-safe") {
                selector := calldataload(callData.offset)
            }
            bytes32 leaf = keccak256(abi.encode(actions[i].adapter, selector));
            if (!MerkleProof.verify(proofs[i], root, leaf)) {
                revert SelectorNotAllowed(i, actions[i].adapter, selector);
            }
            unchecked {
                ++i;
            }
        }
    }
}
