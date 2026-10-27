// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC8192MandatedVault} from "../interfaces/IERC8192MandatedVault.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";

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
            // Exact rational comparison `loss * 10_000 > preAssets * maxDrawdownBps`,
            // evaluated overflow-safely via mulDiv + mulmod remainder (identical
            // semantics to the plain cross-multiplication, which overflow-reverts on
            // assets with extremely large supply and thereby DoSes the breaker).
            uint256 lossBps = Math.mulDiv(loss, 10_000, preAssets);
            uint256 lossBpsRemainder = mulmod(loss, 10_000, preAssets);
            if (lossBps > uint256(maxDrawdownBps) || (lossBps == uint256(maxDrawdownBps) && lossBpsRemainder != 0)) {
                revert IERC8192MandatedVault.DrawdownExceeded();
            }
        }
    }

    /// @dev Checks that single-execution absolute loss does not exceed the mandate's limit.
    /// @param preAssets              Total assets before action execution.
    /// @param postAssets             Total assets after action execution.
    /// @param maxSingleAbsoluteLoss  Maximum allowed absolute single-execution loss.
    function checkSingleAbsoluteLoss(uint256 preAssets, uint256 postAssets, uint256 maxSingleAbsoluteLoss)
        internal
        pure
    {
        if (preAssets > postAssets) {
            uint256 loss = preAssets - postAssets;
            if (loss > maxSingleAbsoluteLoss) {
                revert IERC8192MandatedVault.AbsoluteLossExceeded();
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
            // See checkSingleDrawdown: exact comparison via mulDiv/mulmod,
            // overflow-safe and identical to the plain cross-multiplication.
            uint256 lossBps = Math.mulDiv(cumulativeLoss, 10_000, epochAssets);
            uint256 lossBpsRemainder = mulmod(cumulativeLoss, 10_000, epochAssets);
            if (
                lossBps > uint256(maxCumulativeDrawdownBps)
                    || (lossBps == uint256(maxCumulativeDrawdownBps) && lossBpsRemainder != 0)
            ) {
                revert IERC8192MandatedVault.CumulativeDrawdownExceeded();
            }
        }

        // High-water mark update
        newEpochAssets = postAssets > epochAssets ? postAssets : epochAssets;
    }
}
