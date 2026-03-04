// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Strings} from "@openzeppelin/contracts/utils/Strings.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";
import {VenusAdapter} from "../src/adapters/VenusAdapter.sol";
import {PancakeSwapV3Adapter} from "../src/adapters/PancakeSwapV3Adapter.sol";

import {
    BSC_CHAIN_ID,
    BSC_BUSD,
    BSC_USDT,
    BSC_WBNB,
    BSC_VENUS_COMPTROLLER,
    BSC_VBUSD,
    BSC_VUSDT,
    BSC_VENUS_BUSD_UNDERLYING,
    BSC_VENUS_USDT_UNDERLYING,
    BSC_PANCAKESWAP_V3_ROUTER,
    BSC_PANCAKESWAP_V3_FACTORY,
    IVenusComptroller
} from "./helpers/BscForkConstants.sol";
import {MerkleHelper} from "./helpers/MerkleHelper.sol";

abstract contract VaultForkBscBase is Test {
    using Strings for uint256;

    VaultFactory internal factory;
    VenusAdapter internal venusAdapter;
    PancakeSwapV3Adapter internal pancakeAdapter;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);
    address internal bob = address(0xB0B);

    uint256 internal nonceCounter;

    // Whether setUp rolled the fork to an env-pinned block (BSC_FORK_BLOCK).
    // This is used by guard tests to avoid brittle assertions based on block.number.
    bool internal rolledToPinnedBlock;

    function setUp() public virtual {
        // BSC fork policy for these tests:
        // 1) Default to the provider latest head. Public RPC endpoints often do not retain full
        //    historical trie/state, so forcing a historical block can fail for infrastructure reasons
        //    unrelated to vault logic.
        // 2) Venus/Pancake state can legitimately drift on testnet. Head-by-default keeps smoke checks
        //    aligned with current deployed protocol reality.
        // 3) When deterministic reproduction is required, set BSC_FORK_BLOCK in the environment to pin
        //    execution to a specific block. Only in that case do we attempt rollFork; if rolling fails,
        //    skip with an explicit hint instead of producing a misleading test failure.
        bool hasFork;
        try vm.activeFork() {
            hasFork = true;
        } catch {
            hasFork = false;
        }
        if (!hasFork) {
            vm.skip(true, "fork disabled: run with --fork-url (and --fork-block-number)");
            return;
        }

        if (block.chainid != BSC_CHAIN_ID) {
            vm.skip(true, "unexpected chainid: expected BSC testnet fork");
            return;
        }

        rolledToPinnedBlock = false;
        if (vm.envExists("BSC_FORK_BLOCK")) {
            uint256 forkBlock = vm.envUint("BSC_FORK_BLOCK");
            if (block.number != forkBlock) {
                try vm.rollFork(forkBlock) {
                    rolledToPinnedBlock = true;
                } catch {
                    vm.skip(
                        true,
                        string.concat(
                            "failed to roll fork to BSC_FORK_BLOCK=",
                            forkBlock.toString(),
                            "; default mode uses latest head"
                        )
                    );
                    return;
                }
            }
        }

        // Public RPCs can fail when accessing historical state (e.g., "missing trie node").
        // Treat these infra failures as non-actionable for test semantics.
        try this.assertBscContractsLive() {} catch {
            vm.skip(true, "BSC fork infra failure: cannot read on-chain state (e.g., missing trie node). Use head mode or switch RPC.");
            return;
        }

        authority = vm.addr(authorityKey);
        factory = new VaultFactory();
        venusAdapter = new VenusAdapter();
        pancakeAdapter = new PancakeSwapV3Adapter(BSC_PANCAKESWAP_V3_ROUTER);
    }

    function assertBscContractsLive() external view {
        // External wrapper used to allow try/catch in setUp for infra failures.
        // Intentionally not marked "internal".
        assertGt(BSC_BUSD.code.length, 0, "BUSD missing code");
        assertGt(BSC_USDT.code.length, 0, "USDT missing code");
        assertGt(BSC_WBNB.code.length, 0, "WBNB missing code");

        assertGt(BSC_VENUS_COMPTROLLER.code.length, 0, "Venus comptroller missing code");
        assertGt(BSC_VBUSD.code.length, 0, "vBUSD missing code");
        assertGt(BSC_VUSDT.code.length, 0, "vUSDT missing code");
        assertGt(BSC_VENUS_BUSD_UNDERLYING.code.length, 0, "Venus BUSD underlying missing code");
        assertGt(BSC_VENUS_USDT_UNDERLYING.code.length, 0, "Venus USDT underlying missing code");

        assertGt(BSC_PANCAKESWAP_V3_ROUTER.code.length, 0, "Pancake router missing code");
        assertGt(BSC_PANCAKESWAP_V3_FACTORY.code.length, 0, "Pancake factory missing code");

        address[] memory markets = IVenusComptroller(BSC_VENUS_COMPTROLLER).getAllMarkets();
        assertGt(markets.length, 0, "Venus markets should be non-empty");
    }

    function _nextNonce() internal returns (uint256) {
        return nonceCounter++;
    }

    function _createVault(address asset) internal returns (MandatedVaultClone v) {
        vm.prank(creator);
        v = MandatedVaultClone(
            payable(factory.createVault(asset, "BSC Fork Vault", "bfVAULT", authority, bytes32(nonceCounter)))
        );
    }

    function _sign(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m) internal view returns (bytes memory) {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(authorityKey, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    function _leaf(address addr) internal view returns (bytes32) {
        return keccak256(abi.encode(addr, addr.codehash));
    }

    function _mandate(MandatedVaultClone v, uint256 nonce, uint16 maxDrawdownBps, bytes32 adaptersRoot)
        internal
        view
        returns (IERCXXXXMandatedVault.Mandate memory)
    {
        return IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: maxDrawdownBps,
            maxCumulativeDrawdownBps: maxDrawdownBps,
            allowedAdaptersRoot: adaptersRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
    }

    function _exec(
        MandatedVaultClone v,
        IERCXXXXMandatedVault.Mandate memory m,
        IERCXXXXMandatedVault.Action[] memory actions,
        bytes32[][] memory proofs
    ) internal returns (uint256 pre, uint256 post) {
        bytes memory sig = _sign(v, m);
        vm.prank(executor);
        return v.execute(m, actions, sig, proofs, "");
    }

    function _execRaw(
        MandatedVaultClone v,
        IERCXXXXMandatedVault.Mandate memory m,
        IERCXXXXMandatedVault.Action[] memory actions,
        bytes32[][] memory proofs
    ) internal returns (bool ok, bytes memory ret) {
        bytes memory sig = _sign(v, m);
        bytes memory payload = abi.encodeCall(MandatedVaultClone.execute, (m, actions, sig, proofs, bytes("")));
        vm.prank(executor);
        (ok, ret) = address(v).call(payload);
    }

    function _revertSelector(bytes memory revertData) internal pure returns (bytes4 sel) {
        if (revertData.length < 4) return bytes4(0);
        assembly ("memory-safe") {
            sel := mload(add(revertData, 32))
        }
    }

    function _decodeActionCallFailed(bytes memory revertData)
        internal
        pure
        returns (uint256 index, bytes memory reason)
    {
        require(_revertSelector(revertData) == IERCXXXXMandatedVault.ActionCallFailed.selector, "not ActionCallFailed");
        return abi.decode(_slice(revertData, 4), (uint256, bytes));
    }

    function _decodeErrorString(bytes memory revertData) internal pure returns (string memory message) {
        bytes4 sel = _revertSelector(revertData);
        if (sel == bytes4(0x08c379a0)) return abi.decode(_slice(revertData, 4), (string));

        if (sel == VenusAdapter.VenusMintFailed.selector) {
            uint256 errorCode = abi.decode(_slice(revertData, 4), (uint256));
            return string.concat("VenusMintFailed(", errorCode.toString(), ":", _venusErrorCodeName(errorCode), ")");
        }
        if (sel == VenusAdapter.VenusRedeemFailed.selector) {
            uint256 errorCode = abi.decode(_slice(revertData, 4), (uint256));
            return string.concat("VenusRedeemFailed(", errorCode.toString(), ":", _venusErrorCodeName(errorCode), ")");
        }
        if (sel == VenusAdapter.InsufficientUnderlyingAllowanceFromCaller.selector) {
            (uint256 allowance, uint256 required) = abi.decode(_slice(revertData, 4), (uint256, uint256));
            return string.concat(
                "InsufficientUnderlyingAllowanceFromCaller(", allowance.toString(), "/", required.toString(), ")"
            );
        }
        if (sel == VenusAdapter.InsufficientUnderlyingAllowanceToMarket.selector) {
            (uint256 allowance, uint256 required) = abi.decode(_slice(revertData, 4), (uint256, uint256));
            return string.concat(
                "InsufficientUnderlyingAllowanceToMarket(", allowance.toString(), "/", required.toString(), ")"
            );
        }
        if (sel == VenusAdapter.InsufficientVTokenAllowanceFromCaller.selector) {
            (uint256 allowance, uint256 required) = abi.decode(_slice(revertData, 4), (uint256, uint256));
            return string.concat(
                "InsufficientVTokenAllowanceFromCaller(", allowance.toString(), "/", required.toString(), ")"
            );
        }

        return string.concat("selector=0x", _toHex(sel));
    }

    function _slice(bytes memory data, uint256 start) internal pure returns (bytes memory out) {
        require(start <= data.length, "slice out of bounds");
        out = new bytes(data.length - start);
        for (uint256 i = 0; i < out.length; ++i) {
            out[i] = data[i + start];
        }
    }

    function _venusErrorCodeName(uint256 code) internal pure returns (string memory) {
        if (code == 0) return "NO_ERROR";
        if (code == 1) return "UNAUTHORIZED";
        if (code == 2) return "BAD_INPUT";
        if (code == 3) return "COMPTROLLER_REJECTION";
        if (code == 4) return "COMPTROLLER_CALCULATION_ERROR";
        if (code == 5) return "INTEREST_RATE_MODEL_ERROR";
        if (code == 6) return "INVALID_ACCOUNT_PAIR";
        if (code == 7) return "INVALID_CLOSE_AMOUNT_REQUESTED";
        if (code == 8) return "INVALID_COLLATERAL_FACTOR";
        if (code == 9) return "MATH_ERROR";
        if (code == 10) return "MARKET_NOT_FRESH";
        if (code == 11) return "MARKET_NOT_LISTED";
        if (code == 12) return "TOKEN_INSUFFICIENT_ALLOWANCE";
        if (code == 13) return "TOKEN_INSUFFICIENT_BALANCE";
        if (code == 14) return "TOKEN_INSUFFICIENT_CASH";
        if (code == 15) return "TOKEN_TRANSFER_IN_FAILED";
        if (code == 16) return "TOKEN_TRANSFER_OUT_FAILED";
        return "UNKNOWN";
    }

    function _isVenusProtocolUnavailable(bytes memory innerReason) internal pure returns (bool) {
        bytes4 sel = _revertSelector(innerReason);
        if (sel == VenusAdapter.VenusMintFailed.selector || sel == VenusAdapter.VenusRedeemFailed.selector) {
            uint256 errorCode = abi.decode(_slice(innerReason, 4), (uint256));
            return errorCode == 3 || errorCode == 11 || errorCode == 14;
        }
        if (sel == VenusAdapter.ZeroMintOutput.selector || sel == VenusAdapter.ZeroRedeemOutput.selector) {
            return true;
        }
        if (sel == bytes4(0x08c379a0)) {
            // Error(string)
            string memory message = abi.decode(_slice(innerReason, 4), (string));
            return _containsIgnoreCase(message, "paused");
        }
        return false;
    }

    function _isPancakeProtocolUnavailable(bytes memory innerReason) internal pure returns (bool) {
        bytes4 sel = _revertSelector(innerReason);
        if (sel == bytes4(0x08c379a0)) {
            string memory message = abi.decode(_slice(innerReason, 4), (string));
            return _containsIgnoreCase(message, "pool") || _containsIgnoreCase(message, "liquidity")
                || _containsIgnoreCase(message, "insufficient") || _containsIgnoreCase(message, "stf");
        }
        if (sel == PancakeSwapV3Adapter.DeadlineExpired.selector || sel == bytes4(0x4e487b71)) {
            return false;
        }
        return sel != bytes4(0);
    }

    function _containsIgnoreCase(string memory haystack, string memory needle) internal pure returns (bool) {
        bytes memory haystackLower = _toLowerAscii(bytes(haystack));
        bytes memory needleLower = _toLowerAscii(bytes(needle));

        if (needleLower.length == 0 || haystackLower.length < needleLower.length) return false;

        for (uint256 i = 0; i <= haystackLower.length - needleLower.length; ++i) {
            bool found = true;
            for (uint256 j = 0; j < needleLower.length; ++j) {
                if (haystackLower[i + j] != needleLower[j]) {
                    found = false;
                    break;
                }
            }
            if (found) return true;
        }
        return false;
    }

    function _toLowerAscii(bytes memory value) internal pure returns (bytes memory out) {
        out = new bytes(value.length);
        for (uint256 i = 0; i < value.length; ++i) {
            uint8 c = uint8(value[i]);
            if (c >= 65 && c <= 90) {
                out[i] = bytes1(c + 32);
            } else {
                out[i] = value[i];
            }
        }
    }

    function _toHex(bytes4 data) internal pure returns (string memory out) {
        bytes16 hexSymbols = 0x30313233343536373839616263646566;
        bytes memory str = new bytes(8);
        bytes memory raw = abi.encodePacked(data);
        for (uint256 i = 0; i < 4; ++i) {
            uint8 b = uint8(raw[i]);
            str[i * 2] = bytes1(hexSymbols[b >> 4]);
            str[i * 2 + 1] = bytes1(hexSymbols[b & 0x0f]);
        }
        return string(str);
    }

    function _addressHex(address value) internal pure returns (string memory) {
        return Strings.toHexString(uint256(uint160(value)), 20);
    }

    function _unavailableMessage(string memory prefix, address underlying, address vToken, bytes memory reasonData)
        internal
        pure
        returns (string memory)
    {
        return string.concat(
            prefix,
            " underlying=",
            _addressHex(underlying),
            " market=",
            _addressHex(vToken),
            " reason=",
            _decodeErrorString(reasonData)
        );
    }

    function _rootForPair(address first, address second)
        internal
        view
        returns (bytes32 root, bytes32[] memory firstProof, bytes32[] memory secondProof)
    {
        return MerkleHelper.buildTree2(_leaf(first), _leaf(second));
    }
}
