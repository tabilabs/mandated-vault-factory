// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";
import {AdapterLib} from "../src/libs/AdapterLib.sol";

import {
    FORK_BLOCK,
    USDC,
    WETH,
    DAI,
    USDT,
    AAVE_POOL,
    A_ETH_USDC,
    UNISWAP_ROUTER,
    USDC_WETH_FEE,
    COMPOUND_COMET,
    IAavePool,
    ISwapRouter,
    IComet
} from "./helpers/ForkConstants.sol";
import {MerkleHelper} from "./helpers/MerkleHelper.sol";

/// @title VaultForkTest
/// @notice E2E fork tests against real Ethereum mainnet DeFi protocols.
/// @dev Requires running with a fork backend (`--fork-url`). Skips automatically when not on a fork.
///      Run: ETH_RPC_URL=... forge test --match-path test/VaultFork.t.sol --fork-url $ETH_RPC_URL --fork-block-number 21000000
contract VaultForkTest is Test {
    VaultFactory public factory;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);
    address internal bob = address(0xB0B);

    uint256 internal nonceCounter;

    function setUp() public {
        // Require an active fork backend. vm.activeFork() reverts when no fork is active.
        // Note: fork ID 0 is valid (first fork), so we use a bool to distinguish.
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

        // Hard-gate to Ethereum mainnet fork semantics for these fixed addresses.
        if (block.chainid != 1) {
            vm.skip(true, "unexpected chainid: expected Ethereum mainnet fork");
            return;
        }

        // Ensure determinism even if the runner didn't pin the fork block.
        if (block.number != FORK_BLOCK) {
            try vm.rollFork(FORK_BLOCK) {}
            catch {
                vm.skip(true, "failed to roll fork to FORK_BLOCK");
                return;
            }
        }

        // Deploy our contracts on top of the fork.
        authority = vm.addr(authorityKey);
        factory = new VaultFactory();
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Helpers
    // ═══════════════════════════════════════════════════════════════════

    function _nextNonce() internal returns (uint256) {
        return nonceCounter++;
    }

    function _createVault(address asset) internal returns (MandatedVaultClone v) {
        vm.prank(creator);
        v = MandatedVaultClone(
            payable(factory.createVault(asset, "Fork Vault", "fVAULT", authority, bytes32(nonceCounter)))
        );
    }

    function _sign(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m) internal view returns (bytes memory) {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(authorityKey, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    /// @dev Compute Merkle leaf for an adapter: keccak256(abi.encode(addr, codehash)).
    function _leaf(address addr) internal view returns (bytes32) {
        return keccak256(abi.encode(addr, addr.codehash));
    }

    /// @dev Build a mandate with the given parameters.
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
            maxCumulativeDrawdownBps: maxDrawdownBps, // same as single for simplicity
            allowedAdaptersRoot: adaptersRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
    }

    /// @dev Execute a mandate with actions and proofs.
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

    // ═══════════════════════════════════════════════════════════════════
    //  Part 1: Real Token ERC-4626 Compatibility
    // ═══════════════════════════════════════════════════════════════════

    function test_fork_usdc_depositWithdraw() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 depositAmt = 100e6; // 100 USDC

        deal(USDC, bob, depositAmt);

        vm.startPrank(bob);
        IERC20(USDC).approve(address(v), depositAmt);
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();

        assertGt(shares, 0, "shares should be > 0");
        assertEq(v.totalAssets(), depositAmt, "totalAssets after deposit");

        // Withdraw half
        vm.prank(bob);
        uint256 withdrawn = v.withdraw(depositAmt / 2, bob, bob);
        assertEq(withdrawn, shares / 2, "withdrawn shares");
        assertEq(v.totalAssets(), depositAmt / 2, "totalAssets after partial withdraw");
    }

    function test_fork_dai_depositWithdraw() public {
        MandatedVaultClone v = _createVault(DAI);
        uint256 depositAmt = 100e18; // 100 DAI

        deal(DAI, bob, depositAmt);

        vm.startPrank(bob);
        IERC20(DAI).approve(address(v), depositAmt);
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();

        assertGt(shares, 0, "shares should be > 0");
        assertEq(v.totalAssets(), depositAmt, "totalAssets after deposit");

        // Full redeem
        vm.prank(bob);
        uint256 assets = v.redeem(shares, bob, bob);
        assertEq(assets, depositAmt, "should redeem full amount");
        assertEq(v.totalAssets(), 0, "totalAssets should be 0 after full redeem");
    }

    function test_fork_usdc_mintRedeem() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 mintShares = 50e6;

        // First deposit gives 1:1 ratio, so assets needed = shares
        uint256 assetsNeeded = v.previewMint(mintShares);
        deal(USDC, bob, assetsNeeded);

        vm.startPrank(bob);
        IERC20(USDC).approve(address(v), assetsNeeded);
        uint256 actualAssets = v.mint(mintShares, bob);
        vm.stopPrank();

        assertEq(actualAssets, assetsNeeded, "assets used should match preview");
        assertEq(v.balanceOf(bob), mintShares, "bob should have minted shares");

        // Full redeem
        vm.prank(bob);
        uint256 redeemed = v.redeem(mintShares, bob, bob);
        assertEq(redeemed, actualAssets, "should redeem same assets");
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Part 2: Aave V3 Integration
    // ═══════════════════════════════════════════════════════════════════

    function _aaveMerkle()
        internal
        view
        returns (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof)
    {
        (root, usdcProof, aaveProof) = MerkleHelper.buildTree2(_leaf(USDC), _leaf(AAVE_POOL));
    }

    function test_fork_aave_supply() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _aaveMerkle();
        uint256 nonce = _nextNonce();

        // Actions: approve + supply
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, amount)));
        actions[1] =
            IERCXXXXMandatedVault.Action(AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, amount, address(v), 0)));

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = aaveProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        bytes memory sig = _sign(v, m);

        // Expect MandateExecuted with correct indexed topics (mandateHash, authority, executor).
        // data fields (actionsDigest, preAssets, postAssets) are not checked — preAssets/postAssets
        // depend on execution internals and are already validated by balance assertions below.
        bytes32 expectedHash = v.hashMandate(m);
        vm.expectEmit(true, true, true, false, address(v));
        emit IERCXXXXMandatedVault.MandateExecuted(expectedHash, authority, executor, bytes32(0), 0, 0);

        vm.prank(executor);
        v.execute(m, actions, sig, proofs, "");

        // Verify: vault USDC should be ~0, aUSDC should be ~amount
        assertEq(IERC20(USDC).balanceOf(address(v)), 0, "vault USDC should be 0");
        assertApproxEqAbs(IERC20(A_ETH_USDC).balanceOf(address(v)), amount, 2, "vault aUSDC should be ~amount");
    }

    function test_fork_aave_supply_withPayloadDigestBinding() public {
        // Same as supply(), but binds payloadDigest to the exact actions.
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 1_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _aaveMerkle();
        uint256 nonce = _nextNonce();

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, amount)));
        actions[1] =
            IERCXXXXMandatedVault.Action(AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, amount, address(v), 0)));

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = aaveProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        m.payloadDigest = v.hashActions(actions);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        v.execute(m, actions, sig, proofs, "");

        assertEq(IERC20(USDC).balanceOf(address(v)), 0, "vault USDC should be 0");
        assertApproxEqAbs(IERC20(A_ETH_USDC).balanceOf(address(v)), amount, 2, "aUSDC should be ~amount");
    }

    function test_fork_aave_withdraw() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _aaveMerkle();

        // Step 1: Supply first (pre-position)
        {
            uint256 nonce = _nextNonce();
            IERCXXXXMandatedVault.Action[] memory supplyActions = new IERCXXXXMandatedVault.Action[](2);
            supplyActions[0] =
                IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, amount)));
            supplyActions[1] = IERCXXXXMandatedVault.Action(
                AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, amount, address(v), 0))
            );
            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = aaveProof;

            IERCXXXXMandatedVault.Mandate memory m1 = _mandate(v, nonce, 10000, root);
            _exec(v, m1, supplyActions, proofs);
        }

        // Step 2: Withdraw — preAssets is now 0, so no drawdown issue
        {
            uint256 nonce = _nextNonce();
            IERCXXXXMandatedVault.Action[] memory wdActions = new IERCXXXXMandatedVault.Action[](1);
            wdActions[0] = IERCXXXXMandatedVault.Action(
                AAVE_POOL, 0, abi.encodeCall(IAavePool.withdraw, (USDC, type(uint256).max, address(v)))
            );
            bytes32[][] memory proofs = new bytes32[][](1);
            proofs[0] = aaveProof;

            IERCXXXXMandatedVault.Mandate memory m2 = _mandate(v, nonce, 0, root);
            _exec(v, m2, wdActions, proofs);
        }

        // Verify: USDC back in vault, aUSDC ~0
        assertApproxEqAbs(IERC20(USDC).balanceOf(address(v)), amount, 2, "USDC should be back");
        assertEq(IERC20(A_ETH_USDC).balanceOf(address(v)), 0, "aUSDC should be 0");
    }

    function test_fork_aave_roundTrip() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _aaveMerkle();
        uint256 nonce = _nextNonce();

        // Supply + withdraw in single execution
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](3);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, amount)));
        actions[1] =
            IERCXXXXMandatedVault.Action(AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, amount, address(v), 0)));
        actions[2] = IERCXXXXMandatedVault.Action(
            AAVE_POOL, 0, abi.encodeCall(IAavePool.withdraw, (USDC, type(uint256).max, address(v)))
        );

        bytes32[][] memory proofs = new bytes32[][](3);
        proofs[0] = usdcProof;
        proofs[1] = aaveProof;
        proofs[2] = aaveProof;

        // maxDrawdownBps=50 (~0.5%) — same block, no interest, rounding only
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 50, root);
        (uint256 pre, uint256 post) = _exec(v, m, actions, proofs);

        assertApproxEqAbs(post, pre, 2, "round-trip should preserve assets (within rounding)");
    }

    function test_fork_aave_drawdownTriggered() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _aaveMerkle();
        uint256 nonce = _nextNonce();

        // Supply 60% of USDC
        uint256 supplyAmt = (amount * 60) / 100;
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, supplyAmt)));
        actions[1] = IERCXXXXMandatedVault.Action(
            AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, supplyAmt, address(v), 0))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = aaveProof;

        // maxDrawdownBps=5000 (50%) but we supply 60% → should revert
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 5000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.DrawdownExceeded.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Part 3: Uniswap V3 Integration
    // ═══════════════════════════════════════════════════════════════════

    function _uniswapMerkle()
        internal
        view
        returns (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory routerProof)
    {
        (root, usdcProof, routerProof) = MerkleHelper.buildTree2(_leaf(USDC), _leaf(UNISWAP_ROUTER));
    }

    function test_fork_uniswap_swapExact() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory routerProof) = _uniswapMerkle();
        uint256 nonce = _nextNonce();

        ISwapRouter.ExactInputSingleParams memory swapParams = ISwapRouter.ExactInputSingleParams({
            tokenIn: USDC,
            tokenOut: WETH,
            fee: USDC_WETH_FEE,
            recipient: address(v),
            deadline: block.timestamp + 1,
            amountIn: amount,
            amountOutMinimum: 0,
            sqrtPriceLimitX96: 0
        });

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (UNISWAP_ROUTER, amount)));
        actions[1] =
            IERCXXXXMandatedVault.Action(UNISWAP_ROUTER, 0, abi.encodeCall(ISwapRouter.exactInputSingle, (swapParams)));

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = routerProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        _exec(v, m, actions, proofs);

        assertEq(IERC20(USDC).balanceOf(address(v)), 0, "USDC should be swapped out");
        assertGt(IERC20(WETH).balanceOf(address(v)), 0, "WETH should be received");
    }

    function test_fork_uniswap_withSelectorAllowlist() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 5_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory routerProof) = _uniswapMerkle();
        uint256 nonce = _nextNonce();

        // Build selector allowlist extension
        bytes4 approveSelector = IERC20.approve.selector;
        bytes4 swapSelector = ISwapRouter.exactInputSingle.selector;

        bytes32 selLeaf0 = keccak256(abi.encode(USDC, approveSelector));
        bytes32 selLeaf1 = keccak256(abi.encode(UNISWAP_ROUTER, swapSelector));
        (bytes32 selRoot, bytes32[] memory selProof0, bytes32[] memory selProof1) =
            MerkleHelper.buildTree2(selLeaf0, selLeaf1);

        bytes32[][] memory selectorProofs = new bytes32[][](2);
        selectorProofs[0] = selProof0;
        selectorProofs[1] = selProof1;

        bytes memory selData = abi.encode(selRoot, selectorProofs);
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(keccak256("erc-xxxx:selector-allowlist@v1")), false, selData);
        bytes memory extensions = abi.encode(exts);

        ISwapRouter.ExactInputSingleParams memory swapParams = ISwapRouter.ExactInputSingleParams({
            tokenIn: USDC,
            tokenOut: WETH,
            fee: USDC_WETH_FEE,
            recipient: address(v),
            deadline: block.timestamp + 1,
            amountIn: amount,
            amountOutMinimum: 0,
            sqrtPriceLimitX96: 0
        });

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (UNISWAP_ROUTER, amount)));
        actions[1] =
            IERCXXXXMandatedVault.Action(UNISWAP_ROUTER, 0, abi.encodeCall(ISwapRouter.exactInputSingle, (swapParams)));

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = routerProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        m.extensionsHash = keccak256(extensions);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        v.execute(m, actions, sig, proofs, extensions);

        assertEq(IERC20(USDC).balanceOf(address(v)), 0, "USDC swapped out");
        assertGt(IERC20(WETH).balanceOf(address(v)), 0, "WETH received");
    }

    function test_fork_uniswap_slippageProtection() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory routerProof) = _uniswapMerkle();
        uint256 nonce = _nextNonce();

        // Set amountOutMinimum impossibly high → Uniswap will revert
        ISwapRouter.ExactInputSingleParams memory swapParams = ISwapRouter.ExactInputSingleParams({
            tokenIn: USDC,
            tokenOut: WETH,
            fee: USDC_WETH_FEE,
            recipient: address(v),
            deadline: block.timestamp + 1,
            amountIn: amount,
            amountOutMinimum: type(uint256).max,
            sqrtPriceLimitX96: 0
        });

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (UNISWAP_ROUTER, amount)));
        actions[1] =
            IERCXXXXMandatedVault.Action(UNISWAP_ROUTER, 0, abi.encodeCall(ISwapRouter.exactInputSingle, (swapParams)));

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = routerProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(IERCXXXXMandatedVault.ActionCallFailed.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Part 4: Compound V3 Integration
    // ═══════════════════════════════════════════════════════════════════

    function _compoundMerkle()
        internal
        view
        returns (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory cometProof)
    {
        (root, usdcProof, cometProof) = MerkleHelper.buildTree2(_leaf(USDC), _leaf(COMPOUND_COMET));
    }

    function test_fork_compound_supply() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory cometProof) = _compoundMerkle();
        uint256 nonce = _nextNonce();

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (COMPOUND_COMET, amount)));
        actions[1] = IERCXXXXMandatedVault.Action(COMPOUND_COMET, 0, abi.encodeCall(IComet.supply, (USDC, amount)));

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = cometProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        _exec(v, m, actions, proofs);

        assertEq(IERC20(USDC).balanceOf(address(v)), 0, "vault USDC should be 0");
        assertGt(IComet(COMPOUND_COMET).balanceOf(address(v)), 0, "Comet balance should be > 0");
    }

    function test_fork_compound_roundTrip() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory cometProof) = _compoundMerkle();

        // Step 1: Supply
        {
            uint256 nonce = _nextNonce();
            IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
            actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (COMPOUND_COMET, amount)));
            actions[1] = IERCXXXXMandatedVault.Action(COMPOUND_COMET, 0, abi.encodeCall(IComet.supply, (USDC, amount)));
            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = cometProof;

            IERCXXXXMandatedVault.Mandate memory m1 = _mandate(v, nonce, 10000, root);
            _exec(v, m1, actions, proofs);
        }

        // Step 2: Withdraw
        // After supply, epochAssets is 0 (all USDC sent to Compound). The withdraw brings
        // assets back, which is positive — but cumulative drawdown compares against the
        // epoch high-water mark. We need maxCumulativeDrawdownBps=10000 to allow the full
        // range, since the epoch was initialized at the original amount.
        {
            uint256 nonce = _nextNonce();
            uint256 cometBal = IComet(COMPOUND_COMET).balanceOf(address(v));

            IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
            actions[0] =
                IERCXXXXMandatedVault.Action(COMPOUND_COMET, 0, abi.encodeCall(IComet.withdraw, (USDC, cometBal)));
            bytes32[][] memory proofs = new bytes32[][](1);
            proofs[0] = cometProof;

            // maxDrawdownBps=0 (no single-exec loss), but maxCumulativeDrawdownBps=10000
            // to accommodate the epoch state after supply.
            IERCXXXXMandatedVault.Mandate memory m2 = IERCXXXXMandatedVault.Mandate({
                executor: executor,
                nonce: nonce,
                deadline: 0,
                authorityEpoch: v.authorityEpoch(),
                maxDrawdownBps: 0,
                maxCumulativeDrawdownBps: 10000,
                allowedAdaptersRoot: root,
                payloadDigest: bytes32(0),
                extensionsHash: keccak256("")
            });
            _exec(v, m2, actions, proofs);
        }

        // Rounding tolerance: Compound may truncate by 1 unit
        assertApproxEqAbs(
            IERC20(USDC).balanceOf(address(v)), amount, 10, "USDC should return to vault (within rounding)"
        );
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Part 5: Multi-Protocol Combination
    // ═══════════════════════════════════════════════════════════════════

    function test_fork_multiProtocol_aaveAndUniswap() public {
        MandatedVaultClone v = _createVault(USDC);
        uint256 amount = 10_000e6;
        deal(USDC, address(v), amount);

        // 3-leaf Merkle: USDC + AAVE_POOL + UNISWAP_ROUTER
        bytes32 leafUsdc = _leaf(USDC);
        bytes32 leafAave = _leaf(AAVE_POOL);
        bytes32 leafRouter = _leaf(UNISWAP_ROUTER);
        (bytes32 root, bytes32[][] memory treeProofs) = MerkleHelper.buildTree3(leafUsdc, leafAave, leafRouter);

        uint256 halfAmt = amount / 2;
        uint256 nonce = _nextNonce();

        ISwapRouter.ExactInputSingleParams memory swapParams = ISwapRouter.ExactInputSingleParams({
            tokenIn: USDC,
            tokenOut: WETH,
            fee: USDC_WETH_FEE,
            recipient: address(v),
            deadline: block.timestamp + 1,
            amountIn: halfAmt,
            amountOutMinimum: 0,
            sqrtPriceLimitX96: 0
        });

        // 4 actions: approve(Aave) + supply + approve(Router) + swap
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](4);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, halfAmt)));
        actions[1] = IERCXXXXMandatedVault.Action(
            AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, halfAmt, address(v), 0))
        );
        actions[2] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (UNISWAP_ROUTER, halfAmt)));
        actions[3] =
            IERCXXXXMandatedVault.Action(UNISWAP_ROUTER, 0, abi.encodeCall(ISwapRouter.exactInputSingle, (swapParams)));

        // Proof mapping: USDC=index 0, AAVE=index 1, ROUTER=index 2
        bytes32[][] memory proofs = new bytes32[][](4);
        proofs[0] = treeProofs[0]; // USDC proof
        proofs[1] = treeProofs[1]; // AAVE proof
        proofs[2] = treeProofs[0]; // USDC proof (reused for second approve)
        proofs[3] = treeProofs[2]; // ROUTER proof

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        _exec(v, m, actions, proofs);

        assertEq(IERC20(USDC).balanceOf(address(v)), 0, "all USDC deployed");
        assertGt(IERC20(A_ETH_USDC).balanceOf(address(v)), 0, "aUSDC from Aave");
        assertGt(IERC20(WETH).balanceOf(address(v)), 0, "WETH from Uniswap");
    }

    function test_fork_multiProtocol_merkleProof() public view {
        // Verify that 3-leaf Merkle proofs are independently valid
        bytes32 leafUsdc = _leaf(USDC);
        bytes32 leafAave = _leaf(AAVE_POOL);
        bytes32 leafRouter = _leaf(UNISWAP_ROUTER);
        (bytes32 root, bytes32[][] memory proofs) = MerkleHelper.buildTree3(leafUsdc, leafAave, leafRouter);

        // Verify each leaf independently via OZ MerkleProof
        assertTrue(MerkleProof.verify(proofs[0], root, leafUsdc), "USDC proof valid");
        assertTrue(MerkleProof.verify(proofs[1], root, leafAave), "Aave proof valid");
        assertTrue(MerkleProof.verify(proofs[2], root, leafRouter), "Router proof valid");
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Part 6: Full Lifecycle
    // ═══════════════════════════════════════════════════════════════════

    function test_fork_fullLifecycle() public {
        // 1. Deploy factory (already done in setUp)
        // 2. Create USDC vault
        MandatedVaultClone v = _createVault(USDC);

        // 3. Bob deposits 10,000 USDC
        uint256 depositAmt = 10_000e6;
        deal(USDC, bob, depositAmt);
        vm.startPrank(bob);
        IERC20(USDC).approve(address(v), depositAmt);
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();
        assertEq(shares, depositAmt, "1:1 shares on first deposit");

        // 4-5. Authority mandate: supply all to Aave
        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _aaveMerkle();
        {
            uint256 nonce = _nextNonce();
            IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
            actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, depositAmt)));
            actions[1] = IERCXXXXMandatedVault.Action(
                AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, depositAmt, address(v), 0))
            );
            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = aaveProof;

            IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
            bytes memory sig = _sign(v, m);

            // Verify MandateExecuted event for supply mandate
            vm.expectEmit(true, true, true, false, address(v));
            emit IERCXXXXMandatedVault.MandateExecuted(v.hashMandate(m), authority, executor, bytes32(0), 0, 0);

            vm.prank(executor);
            v.execute(m, actions, sig, proofs, "");
        }

        // 6. Verify aUSDC balance
        assertApproxEqAbs(IERC20(A_ETH_USDC).balanceOf(address(v)), depositAmt, 2, "aUSDC balance");

        // 7-8. Authority mandate: withdraw all from Aave
        {
            uint256 nonce = _nextNonce();
            IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
            actions[0] = IERCXXXXMandatedVault.Action(
                AAVE_POOL, 0, abi.encodeCall(IAavePool.withdraw, (USDC, type(uint256).max, address(v)))
            );
            bytes32[][] memory proofs = new bytes32[][](1);
            proofs[0] = aaveProof;

            IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 0, root);
            bytes memory sig = _sign(v, m);

            // Verify MandateExecuted event for withdraw mandate
            vm.expectEmit(true, true, true, false, address(v));
            emit IERCXXXXMandatedVault.MandateExecuted(v.hashMandate(m), authority, executor, bytes32(0), 0, 0);

            vm.prank(executor);
            v.execute(m, actions, sig, proofs, "");
        }

        // 9. Bob redeems all shares
        vm.prank(bob);
        uint256 redeemed = v.redeem(shares, bob, bob);

        // 10. Verify Bob got back >= 10,000 USDC (same block = exact)
        assertApproxEqAbs(redeemed, depositAmt, 2, "Bob should get back ~10,000 USDC");
        assertApproxEqAbs(IERC20(USDC).balanceOf(bob), depositAmt, 2, "Bob USDC balance");
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Part 7: Security Boundaries
    // ═══════════════════════════════════════════════════════════════════

    function test_fork_unauthorizedProtocol() public {
        MandatedVaultClone v = _createVault(USDC);
        deal(USDC, address(v), 10_000e6);

        // Only USDC in the Merkle tree — Aave is NOT allowed
        bytes32 root = _leaf(USDC);

        uint256 nonce = _nextNonce();
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(
            AAVE_POOL, 0, abi.encodeCall(IAavePool.supply, (USDC, 10_000e6, address(v), 0))
        );
        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.AdapterNotAllowed.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    function test_fork_selectorBlock() public {
        MandatedVaultClone v = _createVault(USDC);
        deal(USDC, address(v), 10_000e6);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _aaveMerkle();
        uint256 nonce = _nextNonce();

        // Selector allowlist: only approve + supply allowed (withdraw must be blocked)
        bytes4 approveSelector = IERC20.approve.selector;
        bytes4 supplySelector = IAavePool.supply.selector;
        bytes32 selLeaf0 = keccak256(abi.encode(USDC, approveSelector));
        bytes32 selLeaf1 = keccak256(abi.encode(AAVE_POOL, supplySelector));
        (bytes32 selRoot, bytes32[] memory selProof0,) = MerkleHelper.buildTree2(selLeaf0, selLeaf1);

        // Build extension with selector allowlist
        bytes32[][] memory selectorProofs = new bytes32[][](2);
        selectorProofs[0] = selProof0; // for USDC.approve
        // For second action (Aave.withdraw), no valid proof exists → build dummy
        selectorProofs[1] = new bytes32[](0);

        bytes memory selData = abi.encode(selRoot, selectorProofs);
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(keccak256("erc-xxxx:selector-allowlist@v1")), false, selData);
        bytes memory extensions = abi.encode(exts);

        // Try to call a selector that is NOT in the allowlist (withdraw instead of supply).
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(USDC, 0, abi.encodeCall(IERC20.approve, (AAVE_POOL, 10_000e6)));
        actions[1] = IERCXXXXMandatedVault.Action(
            AAVE_POOL, 0, abi.encodeCall(IAavePool.withdraw, (USDC, 10_000e6, address(v)))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = aaveProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, nonce, 10000, root);
        m.extensionsHash = keccak256(extensions);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(AdapterLib.SelectorNotAllowed.selector);
        v.execute(m, actions, sig, proofs, extensions);
    }

    function test_fork_proxyCodehashStability() public {
        // Verify proxy contracts have stable codehash
        bytes32 usdcHash = USDC.codehash;
        bytes32 aaveHash = AAVE_POOL.codehash;
        bytes32 cometHash = COMPOUND_COMET.codehash;

        // All should be non-zero (contracts exist at fork block)
        assertTrue(usdcHash != bytes32(0), "USDC has code");
        assertTrue(aaveHash != bytes32(0), "Aave Pool has code");
        assertTrue(cometHash != bytes32(0), "Compound Comet has code");

        // Codehash should be stable across blocks for proxy contracts.
        // (This does not reflect implementation upgrades; it demonstrates why proxy codehash binding
        // does not automatically track implementation changes.)
        vm.rollFork(FORK_BLOCK + 1);
        assertEq(USDC.codehash, usdcHash, "USDC codehash stable across blocks");
        assertEq(AAVE_POOL.codehash, aaveHash, "Aave codehash stable across blocks");
        assertEq(COMPOUND_COMET.codehash, cometHash, "Comet codehash stable across blocks");

        // Merkle leaf should match
        bytes32 leaf = keccak256(abi.encode(USDC, usdcHash));
        assertEq(leaf, _leaf(USDC), "Merkle leaf deterministic");
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Part 8: Token Edge Compatibility (USDT)
    // ═══════════════════════════════════════════════════════════════════

    function test_fork_usdt_asVaultAsset() public {
        MandatedVaultClone v = _createVault(USDT);
        uint256 depositAmt = 100e6; // 100 USDT

        deal(USDT, bob, depositAmt);

        vm.startPrank(bob);
        // USDT approve does NOT return bool — use low-level call to avoid ABI decode revert.
        (bool ok,) = USDT.call(abi.encodeWithSelector(IERC20.approve.selector, address(v), depositAmt));
        require(ok, "USDT approve failed");
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();

        assertGt(shares, 0, "USDT deposit should yield shares");
        assertEq(v.totalAssets(), depositAmt, "totalAssets matches deposit");

        // Withdraw
        vm.prank(bob);
        v.withdraw(depositAmt, bob, bob);

        assertEq(v.totalAssets(), 0, "totalAssets 0 after full withdraw");
    }
}
