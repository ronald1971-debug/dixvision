// ADAPTED FROM: flutter/flutter (BSD-3-Clause)
// C-78 — API client stub for DIX mobile operator cockpit.
//
// This is a PATTERN_ONLY reference — the actual Flutter app is a
// separate project. This file documents the API contract between
// the mobile app and DIX ui/server.py.

import 'dart:convert';

/// Base URL for the DIX operator API.
const String kApiBaseUrl = 'https://dix-operator.local/api';

/// WebSocket URL for live data feeds.
const String kWsUrl = 'wss://dix-operator.local/ws/live';

/// Operator summary response from GET /api/operator/summary.
class OperatorSummary {
  final OperatorMode mode;
  final StrategyCounts strategies;
  final List<EngineRow> engines;

  OperatorSummary({
    required this.mode,
    required this.strategies,
    required this.engines,
  });

  factory OperatorSummary.fromJson(Map<String, dynamic> json) {
    return OperatorSummary(
      mode: OperatorMode.fromJson(json['mode']),
      strategies: StrategyCounts.fromJson(json['strategies']),
      engines: (json['engines'] as List)
          .map((e) => EngineRow.fromJson(e))
          .toList(),
    );
  }
}

/// Current governance mode state.
class OperatorMode {
  final String currentMode;
  final List<String> legalTargets;
  final bool isLocked;

  OperatorMode({
    required this.currentMode,
    required this.legalTargets,
    required this.isLocked,
  });

  factory OperatorMode.fromJson(Map<String, dynamic> json) {
    return OperatorMode(
      currentMode: json['current_mode'] ?? 'LOCKED',
      legalTargets: List<String>.from(json['legal_targets'] ?? []),
      isLocked: json['is_locked'] ?? true,
    );
  }
}

/// Strategy counts across lifecycle states.
class StrategyCounts {
  final int proposed;
  final int canary;
  final int live;
  final int suspended;
  final int retired;

  StrategyCounts({
    required this.proposed,
    required this.canary,
    required this.live,
    required this.suspended,
    required this.retired,
  });

  factory StrategyCounts.fromJson(Map<String, dynamic> json) {
    return StrategyCounts(
      proposed: json['proposed'] ?? 0,
      canary: json['canary'] ?? 0,
      live: json['live'] ?? 0,
      suspended: json['suspended'] ?? 0,
      retired: json['retired'] ?? 0,
    );
  }
}

/// A single engine status row.
class EngineRow {
  final String name;
  final String status;
  final String lastHeartbeat;

  EngineRow({
    required this.name,
    required this.status,
    required this.lastHeartbeat,
  });

  factory EngineRow.fromJson(Map<String, dynamic> json) {
    return EngineRow(
      name: json['name'] ?? '',
      status: json['status'] ?? 'unknown',
      lastHeartbeat: json['last_heartbeat'] ?? '',
    );
  }
}

/// Kill switch response from POST /api/operator/kill.
class KillResponse {
  final bool accepted;
  final String resultMode;
  final String reason;

  KillResponse({
    required this.accepted,
    required this.resultMode,
    required this.reason,
  });

  factory KillResponse.fromJson(Map<String, dynamic> json) {
    return KillResponse(
      accepted: json['accepted'] ?? false,
      resultMode: json['result_mode'] ?? 'LOCKED',
      reason: json['reason'] ?? '',
    );
  }
}

/// DIX Operator API client.
///
/// All methods return typed response objects matching the Pydantic
/// models defined in core/contracts/api/operator.py.
class DixApiClient {
  final String baseUrl;
  final String token;

  DixApiClient({
    this.baseUrl = kApiBaseUrl,
    required this.token,
  });

  /// Headers for authenticated requests.
  Map<String, String> get _headers => {
        'Authorization': 'Bearer $token',
        'Content-Type': 'application/json',
      };

  /// GET /api/operator/summary — fetch current system state.
  Future<OperatorSummary> getSummary() async {
    // In production: http.get(Uri.parse('$baseUrl/operator/summary'), headers: _headers)
    throw UnimplementedError('Stub — implement with http package');
  }

  /// POST /api/operator/kill — emergency halt (requires 2-tap).
  ///
  /// [reason] is the operator-provided justification.
  /// [hmacSignature] is the HMAC-SHA256 signature of the payload.
  Future<KillResponse> killSwitch({
    required String reason,
    required String hmacSignature,
  }) async {
    // In production: http.post(Uri.parse('$baseUrl/operator/kill'), ...)
    throw UnimplementedError('Stub — implement with http package');
  }

  /// POST /api/operator/mode — request governance mode transition.
  Future<KillResponse> requestModeChange({
    required String targetMode,
    required String reason,
    required String hmacSignature,
  }) async {
    // In production: http.post(Uri.parse('$baseUrl/operator/mode'), ...)
    throw UnimplementedError('Stub — implement with http package');
  }
}
