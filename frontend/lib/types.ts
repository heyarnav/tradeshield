export type Role = "client" | "admin";

export interface User {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
}

export interface AccountSummary {
  account_id: string;
  account_number: string;
  cash_balance: number;
  currency: string;
  status: string;
  created_at: string;
}

export interface AccountDetail {
  account_id: string;
  account_number: string;
  cash_balance: number;
  account_status: string;
  holdings_count: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  total_equity: number;
  email: string;
  full_name: string;
  role: Role;
  currency: string;
  created_at: string;
}

export interface PortfolioSummary {
  account_id: string;
  account_number: string;
  cash_balance: number;
  holdings_count: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  total_equity: number;
  account_status: string;
}

export interface Instrument {
  instrument_id: string;
  symbol: string;
  name: string;
  asset_type: string;
  exchange: string;
  current_price: number;
  tick_size: number;
  is_active: boolean;
  price_updated_at: string;
}

export interface Holding {
  holding_id: string;
  instrument_id: string;
  symbol: string;
  name: string;
  asset_type: string;
  current_price: number;
  quantity: number;
  avg_buy_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  opened_at: string;
}

export type OrderSide = "BUY" | "SELL";
export type OrderType = "MARKET" | "LIMIT";

export interface Order {
  order_id: string;
  account_id: string;
  instrument_id: string;
  symbol: string;
  instrument_name: string;
  side: OrderSide;
  order_type: OrderType;
  quantity: number;
  limit_price: number | null;
  status: "PENDING" | "EXECUTED" | "CANCELLED" | "REJECTED";
  risk_status: "CLEAR" | "FLAGGED";
  security_note: string | null;
  threat_indicator_id: string | null;
  execution_price: number | null;
  origin_ip: string;
  referrer_domain: string | null;
  referrer_url: string | null;
  placed_at: string;
  updated_at: string;
  execution_id: string | null;
  executed_quantity: number | null;
  executed_price: number | null;
  gross_amount: number | null;
  executed_at: string | null;
}

export interface ExecutionResult {
  executed: boolean;
  status: string;
  execution_id?: string;
  price?: number;
  gross?: number;
  side?: string;
  reason?: string;
}

export interface OrderListResponse {
  order: Order;
  execution: ExecutionResult | null;
}

export interface LedgerRow {
  transaction_id: string;
  execution_id: string;
  order_id: string;
  side: OrderSide;
  order_type: OrderType;
  symbol: string;
  quantity: number;
  price: number;
  cash_delta: number;
  balance_after: number;
  created_at: string;
}

export interface SecurityDashboard {
  active_threats: number;
  critical_threats: number;
  total_indicators: number;
  disabled_indicators: number;
  threat_sources: number;
  blocked_orders_total: number;
  blocked_orders_24h: number;
  flagged_orders_total: number;
  events_24h: number;
  audit_entries: number;
  client_count: number;
  generated_at: string;
}

export interface Indicator {
  indicator_id: string;
  indicator_type: "ip" | "domain" | "url" | "file_hash";
  value: string;
  threat_category: string;
  confidence: number;
  first_seen: string;
  last_seen: string;
  expires_at: string | null;
  is_active: boolean;
  notes: string | null;
  created_at?: string;
  source_id: string;
  source_name: string;
  reliability: number;
  currently_screening?: boolean;
}

export interface ThreatSource {
  source_id: string;
  name: string;
  description: string | null;
  contact_url: string | null;
  reliability: number;
  is_active: boolean;
  created_at: string;
  indicator_count: number;
  active_indicators: number;
}

export interface BlockedOrderRow {
  event_id: string;
  event_type: "ORDER_BLOCKED" | "ORDER_FLAGGED";
  severity: "low" | "medium" | "high" | "critical";
  detected_at: string;
  account_id: string | null;
  order_id: string | null;
  indicator_id: string | null;
  indicator_type: string | null;
  indicator_value: string | null;
  threat_category: string | null;
  confidence: number | null;
  source_name: string | null;
  attempted_side: string | null;
  attempted_order_type: string | null;
  attempted_quantity: number | null;
  attempted_limit_price: number | null;
  origin_ip: string | null;
  reason: string | null;
  details: Record<string, unknown> | null;
}

export interface SecurityEventRow {
  event_id: string;
  event_type: string;
  severity: string;
  indicator_id: string | null;
  order_id: string | null;
  account_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
  indicator_value: string | null;
  indicator_type: string | null;
  confidence: number | null;
}

export interface AuditRow {
  audit_id: string;
  actor_user_id: string | null;
  actor_role: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  ip_address: string | null;
  status: "success" | "failure";
  created_at: string;
  actor_email: string | null;
}

export interface Paged<T> {
  items: T[];
  total: number;
}

export interface MockBlockchainProof {
  proof_id: string;
  reference_id: string;
  entity_type: string;
  event_type: string;
  record_hash: string;
  blockchain_status: string;
  transaction_hash: string;
  block_number: number;
  network: string;
  contract_address: string;
  created_at: string;
}

export interface MockVerifyResult {
  verified: boolean;
  mock: boolean;
  record_hash: string;
  transaction_hash: string;
  block_number: number;
  network: string;
  contract_address: string;
  recomputed_record_hash: string;
}
