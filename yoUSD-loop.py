import requests
from typing import Dict, Optional, Tuple

MORPHO_GRAPHQL_URL = "https://api.morpho.org/graphql"
BASE_CHAIN_ID = 8453
MORPHO_MARKET_UNIQUE_KEY = "0x1a3e69d0109bb1be42b80e11034bb6ee98fc466721f26845dc83b2aa8d979137"
VAULT_ADDRESS = "0x0000000f2eB9f69274678c76222B35eEc7588a65"
YO_API_BASE = "https://api.yo.xyz/api/v1"
LTV_LIMIT = 0.86
LABEL_WIDTH = 28


class YoDataClient:
    def __init__(
        self,
        yo_api_base: str = YO_API_BASE,
        morpho_graphql_url: str = MORPHO_GRAPHQL_URL,
    ):
        self.yo_api_base = yo_api_base
        self.morpho_graphql_url = morpho_graphql_url
        self.session = requests.Session()

    def fetch_yo_vault_stats(
        self, vault_addr: str = VAULT_ADDRESS, chain_id: int = BASE_CHAIN_ID
    ) -> Tuple[Optional[Dict], Optional[str]]:
        try:
            r = self.session.get(f"{self.yo_api_base}/vault/stats", timeout=20)
            r.raise_for_status()
            j = r.json()
        except requests.RequestException as exc:
            return None, f"network_error: {exc}"
        except ValueError as exc:
            return None, f"json_error: {exc}"
        items = j.get("data") or []
        target = None
        for it in items:
            share_addr = ((it.get("shareAsset") or {}).get("address") or "").lower()
            cid = ((it.get("chain") or {}).get("id"))
            vid = it.get("id")
            if share_addr == vault_addr.lower() and cid == chain_id and vid == "yoUSD":
                target = it
                break
        if not target:
            return None, "vault_not_found"
        asset = target.get("asset") or {}
        share_price = target.get("sharePrice") or {}
        y = target.get("yield") or {}

        def _to_float(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return None

        return (
            {
                "vault_symbol": ((target.get("shareAsset") or {}).get("symbol"))
                or target.get("name")
                or target.get("id"),
                "asset_address": asset.get("address"),
                "asset_symbol": asset.get("symbol"),
                "share_price": _to_float(share_price.get("formatted")),
                "yield_1d": (_to_float(y.get("1d")) / 100.0)
                if _to_float(y.get("1d")) is not None
                else None,
                "yield_7d": (_to_float(y.get("7d")) / 100.0)
                if _to_float(y.get("7d")) is not None
                else None,
                "yield_30d": (_to_float(y.get("30d")) / 100.0)
                if _to_float(y.get("30d")) is not None
                else None,
            },
            None,
        )

    def fetch_morpho_market_info(
        self, unique_key: str = MORPHO_MARKET_UNIQUE_KEY, chain_id: int = BASE_CHAIN_ID
    ) -> Tuple[Optional[Dict], Optional[str]]:
        q = """
        query MarketInfo($uk: String!, $cid: Int!) {
          marketByUniqueKey(uniqueKey: $uk, chainId: $cid) {
            lltv
            state {
              borrowApy
              avgBorrowApy
              avgNetBorrowApy
              supplyApy
              avgSupplyApy
              avgNetSupplyApy
              rewards { supplyApr borrowApr }
            }
          }
        }
        """
        try:
            r = self.session.post(
                self.morpho_graphql_url,
                json={"query": q, "variables": {"uk": unique_key, "cid": chain_id}},
                timeout=20,
            )
            r.raise_for_status()
            payload = r.json()
            data = payload["data"]["marketByUniqueKey"]
        except requests.RequestException as exc:
            return None, f"network_error: {exc}"
        except (ValueError, KeyError, TypeError) as exc:
            return None, f"parse_error: {exc}"
        state = data.get("state", {})
        return (
            {
                "lltv": float(data.get("lltv")) if data.get("lltv") is not None else None,
                "borrowApy": float(state.get("borrowApy"))
                if state.get("borrowApy") is not None
                else None,
                "avgBorrowApy": float(state.get("avgBorrowApy"))
                if state.get("avgBorrowApy") is not None
                else None,
                "avgNetBorrowApy": float(state.get("avgNetBorrowApy"))
                if state.get("avgNetBorrowApy") is not None
                else None,
                "supplyApy": float(state.get("supplyApy"))
                if state.get("supplyApy") is not None
                else None,
                "avgSupplyApy": float(state.get("avgSupplyApy"))
                if state.get("avgSupplyApy") is not None
                else None,
                "avgNetSupplyApy": float(state.get("avgNetSupplyApy"))
                if state.get("avgNetSupplyApy") is not None
                else None,
                "rewards": state.get("rewards"),
            },
            None,
        )


def fmt_label(label: str) -> str:
    return label.ljust(LABEL_WIDTH)


def fmt_rate(rate: float) -> str:
    return f"{rate:.2%}"


def fmt_usd(value: float) -> str:
    return f"${value:,.2f}"


def get_float_input(prompt):
    while True:
        try:
            value = float(input(prompt))
            return value
        except ValueError:
            print("Invalid input. Please enter a numeric value.")


def get_int_input(prompt):
    while True:
        try:
            value = int(input(prompt))
            return value
        except ValueError:
            print("Invalid input. Please enter an integer value.")

def get_str_input(prompt, default=None):
    while True:
        s = input(prompt)
        if s.strip() == "" and default is not None:
            return default
        if s.strip():
            return s.strip()

def choose_yo_apy(yo_stats, window):
    if not yo_stats:
        return 0.0, "unavailable", "vault APY unavailable"
    w = (window or "7d").lower()
    if w not in {"1d", "7d", "30d"}:
        w = "7d"
    mapping = {
        "1d": yo_stats.get("yield_1d"),
        "7d": yo_stats.get("yield_7d"),
        "30d": yo_stats.get("yield_30d"),
    }
    preferred = []
    for key in [w, "7d", "1d", "30d"]:
        if key not in preferred:
            preferred.append(key)
    for idx, key in enumerate(preferred):
        value = mapping.get(key)
        if value is not None:
            if idx == 0:
                return value, key, ""
            return value, key, f"fallback to {key}"
    return 0.0, "unavailable", "vault APY unavailable"


def choose_borrow_apy(market, mode):
    if not market:
        return 0.0, "unavailable"
    m = (mode or "net").lower()
    if m not in {"spot", "avg", "net"}:
        m = "net"
    if m == "net":
        val = market.get("avgNetBorrowApy")
        if val is None:
            val = market.get("borrowApy") if market.get("borrowApy") is not None else market.get("avgBorrowApy")
        return float(val or 0.0), "net"
    if m == "avg":
        val = market.get("avgBorrowApy") if market.get("avgBorrowApy") is not None else market.get("borrowApy")
        return float(val or 0.0), "avg"
    val = market.get("borrowApy") if market.get("borrowApy") is not None else market.get("avgBorrowApy")
    return float(val or 0.0), "spot"


def run_looping_calculation(initial, max_borrow_per_loop, loops, ltv_limit, yo_apy, bor_apy):
    assets_usdc = initial
    borrow_usdc = 0.0
    loops_executed = 0
    for _ in range(loops):
        allowed_by_limit = max(0.0, (ltv_limit * assets_usdc - borrow_usdc) / (1.0 - ltv_limit))
        take = min(max_borrow_per_loop, allowed_by_limit)
        if take <= 0.0:
            break
        borrow_usdc += take
        assets_usdc += take
        loops_executed += 1
    ltv_after = (borrow_usdc / assets_usdc) if assets_usdc > 0 else 0.0
    yearly_profit_yield = assets_usdc * yo_apy
    yearly_borrow_cost = borrow_usdc * bor_apy
    net_yearly_profit = yearly_profit_yield - yearly_borrow_cost
    net_apy_on_equity = (net_yearly_profit / initial) if initial > 0 else 0.0
    eff_leverage = (assets_usdc / (assets_usdc - borrow_usdc)) if (assets_usdc - borrow_usdc) > 0 else 1.0
    return {
        "assets_usdc": assets_usdc,
        "borrow_usdc": borrow_usdc,
        "loops_executed": loops_executed,
        "ltv_after": ltv_after,
        "yearly_profit_yield": yearly_profit_yield,
        "yearly_borrow_cost": yearly_borrow_cost,
        "net_yearly_profit": net_yearly_profit,
        "net_apy_on_equity": net_apy_on_equity,
        "eff_leverage": eff_leverage,
    }


def calculate_net_apy():
    client = YoDataClient()
    while True:
        print("=" * 60)
        print("yoUSD Looping Calculator")
        print("=" * 60)
        print()

        print("Fetching live data (from Morpho on Base)...")
        yo_stats, yo_error = client.fetch_yo_vault_stats(VAULT_ADDRESS, BASE_CHAIN_ID)
        market, market_error = client.fetch_morpho_market_info()

        redeem_rate = yo_stats.get("share_price") if yo_stats else None
        vault_symbol = yo_stats.get("vault_symbol") if yo_stats else None
        asset_addr = yo_stats.get("asset_address") if yo_stats else None
        asset_sym = yo_stats.get("asset_symbol") if yo_stats else None

        win = get_str_input("Vault APY window (1d/7d/30d) [7d]: ", "7d").lower()
        if win not in {"1d", "7d", "30d"}:
            win = "7d"
        mode = get_str_input("Borrow APY mode (spot/avg/net) [net]: ", "net").lower()
        if mode not in {"spot", "avg", "net"}:
            mode = "net"

        yo_apy, yo_window_used, yo_msg = choose_yo_apy(yo_stats, win)
        bor_apy, borrow_mode_used = choose_borrow_apy(market, mode)

        print()
        print("DATA USED")
        print("-" * 60)
        if vault_symbol:
            print(f"{fmt_label('Vault Token:')}{vault_symbol}")
        else:
            print(f"{fmt_label('Vault Token:')}unavailable")
        if asset_addr:
            if asset_sym:
                print(f"{fmt_label('Underlying Asset:')}{asset_addr} ({asset_sym})")
            else:
                print(f"{fmt_label('Underlying Asset:')}{asset_addr}")
        else:
            print(f"{fmt_label('Underlying Asset:')}unavailable")
        if redeem_rate is not None:
            print(f"{fmt_label('Redeem Rate (USDC/share):')}{redeem_rate:,.8f}")
        else:
            print(f"{fmt_label('Redeem Rate (USDC/share):')}unavailable")
        print(f"{fmt_label('Vault APY:')}{fmt_rate(yo_apy)} [{yo_window_used}] ({yo_msg})")
        print(f"{fmt_label('Borrow APY:')}{fmt_rate(bor_apy)} [{borrow_mode_used}]")
        if yo_error:
            print(f"{fmt_label('Vault data status:')}{yo_error}")
        if market_error:
            print(f"{fmt_label('Market data status:')}{market_error}")

        print()
        print("Please enter the following values:")
        print()
        initial = get_float_input("Base investment (USDC): ")
        preview_max = max(0.0, LTV_LIMIT * initial)
        max_borrow_per_loop = get_float_input(f"Max borrow per loop (USDC) [max {preview_max:,.2f}]: ")
        if max_borrow_per_loop < 0:
            max_borrow_per_loop = 0.0
        if max_borrow_per_loop == 0.0:
            max_loops_allowed = 0
        else:
            max_loops_allowed = int((LTV_LIMIT * initial) / ((1.0 - LTV_LIMIT) * max_borrow_per_loop))
            if max_loops_allowed < 0:
                max_loops_allowed = 0
        loops = get_int_input(f"Number of loops [max {max_loops_allowed}]: ")
        if loops < 0 or loops > max_loops_allowed:
            print(f"Loops must be between 0 and {max_loops_allowed}. Exiting.")
            return

        print()
        print("=" * 60)
        print("CALCULATING...")
        print("=" * 60)
        print()

        results = run_looping_calculation(
            initial=initial,
            max_borrow_per_loop=max_borrow_per_loop,
            loops=loops,
            ltv_limit=LTV_LIMIT,
            yo_apy=yo_apy,
            bor_apy=bor_apy,
        )

        print("RESULTS:")
        print("-" * 60)
        print(f"{fmt_label('Gross Assets (USDC):')}{fmt_usd(results['assets_usdc'])}")
        print(f"{fmt_label('Effective Leverage:')}{results['eff_leverage']:.2f}x")
        print(f"{fmt_label('LTV After Leverage:')}{fmt_rate(results['ltv_after'])}")
        print(f"{fmt_label('Net Borrowed USDC:')}{fmt_usd(results['borrow_usdc'])}")
        print(f"{fmt_label('Loops Executed:')}{results['loops_executed']}")
        print(f"{fmt_label('Looped Supply APY:')}{fmt_rate(yo_apy)}")
        print(f"{fmt_label('Yearly Yield on Assets:')}{fmt_usd(results['yearly_profit_yield'])}")
        print(f"{fmt_label('Yearly Borrow Cost:')}{fmt_usd(results['yearly_borrow_cost'])}")
        print(f"{fmt_label('Net Yearly Profit:')}{fmt_usd(results['net_yearly_profit'])}")
        print("-" * 60)
        print(f"{fmt_label('Net APY on Initial Deposit:')}{fmt_rate(results['net_apy_on_equity'])}")
        print("=" * 60)
        print()

        again = input("Calculate again? (y/n): ").lower()
        if again != "y":
            break
        print("\n" * 2)

if __name__ == "__main__":
    calculate_net_apy()
