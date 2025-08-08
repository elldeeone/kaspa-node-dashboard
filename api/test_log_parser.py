#!/usr/bin/env python3
"""
Test script for the log parser module.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log_parser import KaspadLogParser

def test_log_parser():
    """Test the log parser with sample log data."""
    
    # Create a test log file
    test_log_path = "/tmp/test_kaspad.log"
    
    sample_logs = """
2025-01-08T10:00:00.123Z INFO  Application version: 0.13.4
2025-01-08T10:00:01.456Z INFO  Starting Kaspad node
2025-01-08T10:00:05.789Z INFO  Peer 192.168.1.100:16111 connected
2025-01-08T10:00:06.123Z INFO  Outbound connection to 10.0.0.50:16111 established
2025-01-08T10:00:07.456Z INFO  IBD peer selected: 192.168.1.100:16111
2025-01-08T10:00:10.789Z INFO  Peer 172.16.0.25:16111 connected
2025-01-08T10:00:15.123Z WARN  Peer 172.16.0.25:16111 disconnected
2025-01-08T10:00:20.456Z INFO  Current peers: 2
2025-01-08T10:00:25.789Z INFO  Syncing headers from IBD peer 192.168.1.100:16111
"""
    
    # Write sample logs to test file
    with open(test_log_path, 'w') as f:
        f.write(sample_logs)
    
    # Initialize parser with test file
    parser = KaspadLogParser(test_log_path)
    
    # Parse the logs
    result = parser.parse_logs()
    
    print("Log Parser Test Results:")
    print("-" * 50)
    print(f"Uptime: {result['uptime']}")
    print(f"Uptime seconds: {result['uptime_seconds']}")
    print(f"Node start time: {result['node_start_time']}")
    print(f"Log available: {result['log_available']}")
    print("\nPeer Information:")
    print(f"  Total peers: {result['peer_info']['peer_count']}")
    print(f"  IBD peers: {result['peer_info']['ibd_peers']}")
    print(f"  Outbound peers: {result['peer_info']['outbound_peers']}")
    print(f"  Inbound peers: {result['peer_info']['inbound_peers']}")
    print("\nPeer List:")
    for peer in result['peer_info']['peers']:
        print(f"  - {peer['ip']}:{peer['port']}")
        print(f"    Outbound: {peer['is_outbound']}, IBD: {peer['is_ibd']}")
        print(f"    Connected for: {peer['connected_time']}s")
    
    # Clean up
    os.remove(test_log_path)
    
    print("\n✅ Test completed successfully!")

if __name__ == "__main__":
    test_log_parser()