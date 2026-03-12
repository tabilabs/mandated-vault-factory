// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {BaseDeploymentJson} from "./helpers/BaseDeploymentJson.sol";

contract BaseDeploymentJsonTest is Test {
    function test_baseDeploymentJson_isCompleteRaw_returnsFalseWhenKeyMissing() public view {
        string memory raw = '{"factory":"0x1234","adapters":{"aave":"0x1234"}}';
        assertFalse(BaseDeploymentJson.isCompleteRaw(raw), "missing keys should be treated as incomplete");
    }

    function test_baseDeploymentJson_isCompleteRaw_returnsFalseWhenPlaceholderPresent() public view {
        string memory raw = string.concat(
            "{",
            '"factory":"<fill>",',
            '"factoryCodehash":"0x0",',
            '"factoryLeaf":"0x0",',
            '"adapters":{"aave":"0x1","morpho":"0x1","uniswap":"0x1","aerodrome":"0x1","compound":"0x1"},',
            '"adapterCodehashes":{"aave":"0x1","morpho":"0x1","uniswap":"0x1","aerodrome":"0x1","compound":"0x1"},',
            '"adapterLeaves":{"aave":"0x1","morpho":"0x1","uniswap":"0x1","aerodrome":"0x1","compound":"0x1"}',
            "}"
        );
        assertFalse(BaseDeploymentJson.isCompleteRaw(raw), "placeholders should be treated as incomplete");
    }
}
