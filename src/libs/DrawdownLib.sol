// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERCXXXXMandatedVault} from "../interfaces/IERCXXXXMandatedVault.sol";

/// @title DrawdownLib
/// @notice Circuit breaker logic for single-execution and cumulative drawdown checks.
/// @dev Extracted from MandatedVaultClone.execute() step 16.
library DrawdownLib {
    /// @dev Checks that single-execution drawdown does not exceed the mandate's limit.
    /// @param preAssets      Total assets before action execution.
    /// @param postAssets     Total assets after action execution.
    /// @param maxDrawdownBps Maximum allowed single-execution drawdown in basis points.
    function checkSingleDrawdown(uint256 preAssets, uint256 postAssets, uint16 maxDrawdownBps) internal pure {
        if (preAssets != 0 && preAssets > postAssets) {
            uint256 loss = preAssets - postAssets;
            if (loss * 10_000 > preAssets * uint256(maxDrawdownBps)) {
                revert IERCXXXXMandatedVault.DrawdownExceeded();
            }
        }
    }

    /// @dev Checks that cumulative drawdown since epoch start does not exceed the mandate's limit.
    ///      Also updates the epoch high-water mark if postAssets exceeds it.
    /// @param epochAssets              Epoch high-water mark (assets at epoch start or last HWM).
    /// @param postAssets               Total assets after action execution.
    /// @param maxCumulativeDrawdownBps Maximum allowed cumulative drawdown in basis points.
    /// @return newEpochAssets           Updated epoch assets (HWM update if applicable).
    function checkCumulativeDrawdown(uint256 epochAssets, uint256 postAssets, uint16 maxCumulativeDrawdownBps)
        internal
        pure
        returns (uint256 newEpochAssets)
    {
        if (epochAssets != 0 && epochAssets > postAssets) {
            uint256 cumulativeLoss = epochAssets - postAssets;
            if (cumulativeLoss * 10_000 > epochAssets * uint256(maxCumulativeDrawdownBps)) {
                revert IERCXXXXMandatedVault.CumulativeDrawdownExceeded();
            }
        }

        // High-water mark update
        newEpochAssets = postAssets > epochAssets ? postAssets : epochAssets;
    }
}
