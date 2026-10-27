// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {DrawdownLib} from "../src/libs/DrawdownLib.sol";
import {IERC8192MandatedVault} from "../src/interfaces/IERC8192MandatedVault.sol";

/// @notice Regression tests for the overflow-safe, exact drawdown comparison.
///         The previous implementation cross-multiplied (`loss * 10_000 > assets * bps`),
///         which panics on assets with very large supply (DoS of the circuit breaker)
///         and, if naively replaced with a floored mulDiv, silently tolerates tiny losses.
contract DrawdownLibTest is Test {
    // External wrappers: expectRevert needs a sub-call, while internal library
    // functions are inlined into this contract (same call depth as the cheatcode).
    function extSingle(uint256 preAssets, uint256 postAssets, uint16 maxDrawdownBps) external pure {
        DrawdownLib.checkSingleDrawdown(preAssets, postAssets, maxDrawdownBps);
    }

    function extCumulative(uint256 epochAssets, uint256 postAssets, uint16 maxCumulativeDrawdownBps) external pure {
        DrawdownLib.checkCumulativeDrawdown(epochAssets, postAssets, maxCumulativeDrawdownBps);
    }

    function test_singleDrawdown_anyLossRevertsWhenLimitZero() public {
        // 1 wei of loss with a 0 bps limit must revert (no floor-rounding tolerance).
        vm.expectRevert(IERC8192MandatedVault.DrawdownExceeded.selector);
        this.extSingle(10_000, 9_999, 0);
    }

    function test_singleDrawdown_lossWithinLimitPasses() public {
        // 1% loss with a 200 bps limit is allowed.
        DrawdownLib.checkSingleDrawdown(100_000, 99_000, 200);
    }

    function test_singleDrawdown_exactBoundaryWithRemainderReverts() public {
        // 10000/3 = 3333.33 bps > 3333 bps limit: remainder must tip the comparison.
        vm.expectRevert(IERC8192MandatedVault.DrawdownExceeded.selector);
        this.extSingle(3, 2, 3333);
    }

    function test_singleDrawdown_hugeAssetsNoOverflowPanic() public {
        // Cross-multiplication used to overflow here (2**255 * 10_000 > 2**256)
        // and panic instead of evaluating the breaker: must revert with the
        // custom error instead.
        uint256 huge = 1 << 255;
        vm.expectRevert(IERC8192MandatedVault.DrawdownExceeded.selector);
        this.extSingle(huge, 0, 0);
    }

    function test_singleDrawdown_hugeAssetsSmallLossWithinLimit() public {
        uint256 huge = 1 << 255;
        // 1 wei on 2**255 is far below 1 bps: must not revert.
        DrawdownLib.checkSingleDrawdown(huge, huge - 1, 1);
    }

    function test_cumulativeDrawdown_anyLossRevertsWhenLimitZero() public {
        vm.expectRevert(IERC8192MandatedVault.CumulativeDrawdownExceeded.selector);
        this.extCumulative(10_000, 9_999, 0);
    }

    function test_cumulativeDrawdown_hugeAssetsNoOverflowPanic() public {
        uint256 huge = 1 << 255;
        vm.expectRevert(IERC8192MandatedVault.CumulativeDrawdownExceeded.selector);
        this.extCumulative(huge, 0, 0);
    }

    function test_cumulativeDrawdown_updatesHighWaterMark() public {
        uint256 newHwm = DrawdownLib.checkCumulativeDrawdown(50_000, 60_000, 0);
        assertEq(newHwm, 60_000, "HWM must move up on growth");
        uint256 unchanged = DrawdownLib.checkCumulativeDrawdown(50_000, 40_000, 10_000);
        assertEq(unchanged, 50_000, "HWM must stay put on loss");
    }
}
