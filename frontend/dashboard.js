/**
 * Kaspa Node Dashboard JavaScript
 * Handles real-time data fetching and UI updates
 */

class KaspaDashboard {
    constructor() {
        this.updateInterval = 5000; // 5 seconds
        this.phaseClassMap = {
            'Negotiation': 'phase-negotiation',
            'Headers Proof': 'phase-headers-proof',
            'Block Download': 'phase-block-download',
            'Post-Processing': 'phase-post-processing',
            'Complete': 'phase-complete',
            'Error': 'phase-error'
        };
        
        this.elements = this.cacheElements();
        this.init();
    }
    
    /**
     * Cache DOM elements for performance
     */
    cacheElements() {
        return {
            // Node status elements
            syncStatus: document.getElementById('syncStatus'),
            version: document.getElementById('version'),
            p2pId: document.getElementById('p2pId'),
            network: document.getElementById('network'),
            utxoIndexed: document.getElementById('utxoIndexed'),
            uptime: document.getElementById('uptime'),
            
            // Sync progress elements
            syncPhase: document.getElementById('syncPhase'),
            syncSubPhase: document.getElementById('syncSubPhase'),
            subPhaseContainer: document.getElementById('subPhaseContainer'),
            progressText: document.getElementById('progressText'),
            progressFill: document.getElementById('progressFill'),
            syncDetails: document.getElementById('syncDetails'),
            syncPeerAddress: document.getElementById('syncPeerAddress'),
            peerAddressContainer: document.getElementById('peerAddressContainer'),
            syncError: document.getElementById('syncError'),
            syncErrorContainer: document.getElementById('syncErrorContainer'),
            
            // Blockchain stats elements
            blockCount: document.getElementById('blockCount'),
            headerCount: document.getElementById('headerCount'),
            blueScore: document.getElementById('blueScore'),
            difficulty: document.getElementById('difficulty'),
            mempoolSize: document.getElementById('mempoolSize'),
            
            // Peer overview elements
            connectedPeers: document.getElementById('connectedPeers'),
            peerDirection: document.getElementById('peerDirection'),
            ibdPeers: document.getElementById('ibdPeers'),
            averagePing: document.getElementById('averagePing'),
            peerVersions: document.getElementById('peerVersions'),
            peerList: document.getElementById('peerList'),
            
            // Update time
            lastUpdate: document.getElementById('lastUpdate')
        };
    }
    
    /**
     * Initialize the dashboard
     */
    init() {
        this.fetchData();
        setInterval(() => this.fetchData(), this.updateInterval);
    }
    
    /**
     * Format numbers for display
     */
    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }
    
    /**
     * Format hash for display
     */
    formatHash(hash) {
        if (!hash || hash === 'unknown') return 'Unknown';
        if (hash.length > 16) {
            return `${hash.substring(0, 8)}...${hash.substring(hash.length - 8)}`;
        }
        return hash;
    }
    
    /**
     * Format duration in seconds to human readable
     */
    formatDuration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;
        
        if (hours > 0) {
            return `${hours}h ${minutes}m ${secs}s`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    }
    
    /**
     * Update peer versions display
     */
    updatePeerVersions(versions) {
        const container = this.elements.peerVersions;
        
        // Clear existing content
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        
        Object.entries(versions).forEach(([version, count]) => {
            const badge = document.createElement('div');
            badge.className = 'version-badge';
            badge.textContent = `v${version} (${count})`;
            container.appendChild(badge);
        });
    }
    
    /**
     * Update peer list display
     */
    updatePeerList(peers) {
        const container = this.elements.peerList;
        
        if (peers.length === 0) {
            container.innerHTML = '<div style=\"text-align: center; color: #7f8c8d; padding: 20px;\">No peers connected</div>';
            return;
        }
        
        // Clear existing content
        while (container.firstChild) {
            container.removeChild(container.firstChild);
        }
        
        peers.forEach(peer => {
            const item = document.createElement('div');
            item.className = 'peer-item';
            
            const version = peer.version.includes('kaspad:') ? 
                peer.version.split('kaspad:')[1].split('/')[0] : 
                peer.version;
            
            const badges = [];
            if (peer.is_outbound) badges.push('<span class=\"badge badge-outbound\">OUT</span>');
            if (!peer.is_outbound) badges.push('<span class=\"badge badge-inbound\">IN</span>');
            if (peer.is_ibd) badges.push('<span class=\"badge badge-ibd\">IBD</span>');
            
            item.innerHTML = `
                <div class=\"peer-info\">
                    <div class=\"peer-ip\">${peer.ip}:${peer.port}</div>
                    <div class=\"peer-version\">v${version}</div>
                    <div class=\"peer-badges\">${badges.join('')}</div>
                </div>
                <div class=\"peer-stats\">
                    <div class=\"peer-ping\">${peer.ping}ms</div>
                    <div style=\"font-size: 0.7em; color: #95a5a6;\">
                        ${this.formatDuration(peer.connected_time)}
                    </div>
                </div>
            `;
            
            container.appendChild(item);
        });
    }
    
    /**
     * Update sync phase display with appropriate badge
     */
    updateSyncPhase(phase) {
        this.elements.syncPhase.textContent = phase;
        
        // Add appropriate badge based on phase
        let badgeClass = '';
        for (const [keyword, className] of Object.entries(this.phaseClassMap)) {
            if (phase.includes(keyword)) {
                badgeClass = className;
                break;
            }
        }
        
        if (badgeClass) {
            const badge = document.createElement('span');
            badge.className = `phase-badge ${badgeClass}`;
            badge.textContent = 'IBD';
            this.elements.syncPhase.appendChild(badge);
        }
    }
    
    /**
     * Update conditional display elements
     */
    updateConditionalDisplay(container, value, textElement) {
        if (value) {
            container.style.display = 'flex';
            textElement.textContent = typeof value === 'string' ? value : value.replace(/_/g, ' ');
        } else {
            container.style.display = 'none';
        }
    }
    
    /**
     * Main data fetching and update function
     */
    async fetchData() {
        try {
            const [kaspadResponse, blockdagResponse, peersResponse] = await Promise.all([
                fetch('/api/info/kaspad'),
                fetch('/api/info/blockdag'),
                fetch('/api/info/peers')
            ]);
            
            if (!kaspadResponse.ok || !blockdagResponse.ok || !peersResponse.ok) {
                throw new Error('API request failed');
            }
            
            const kaspadData = await kaspadResponse.json();
            const blockdagData = await blockdagResponse.json();
            const peersData = await peersResponse.json();
            
            this.updateNodeStatus(kaspadData);
            this.updateSyncProgress(kaspadData.syncProgress || {});
            this.updateBlockchainStats(kaspadData, blockdagData);
            this.updateNetworkStats(peersData);
            
            this.elements.lastUpdate.textContent = new Date().toLocaleString();
            
        } catch (error) {
            this.handleError(error);
        }
    }
    
    /**
     * Update node status section
     */
    updateNodeStatus(kaspadData) {
        this.elements.syncStatus.textContent = kaspadData.isSynced ? 'Synchronized' : 'Syncing';
        this.elements.syncStatus.className = kaspadData.isSynced ? 'status-ready' : 'status-syncing';
        this.elements.version.textContent = kaspadData.version || 'Unknown';
        this.elements.p2pId.textContent = kaspadData.p2pId || 'Unknown';
        this.elements.network.textContent = kaspadData.networkName || 'Unknown';
        this.elements.utxoIndexed.textContent = kaspadData.hasUtxoIndex ? 'Yes' : 'No';
        this.elements.uptime.textContent = kaspadData.uptime?.uptime_formatted || 'Unknown';
    }
    
    /**
     * Update sync progress section
     */
    updateSyncProgress(syncProgress) {
        const phase = syncProgress.phase || 'Unknown';
        
        // Clear and update phase display
        while (this.elements.syncPhase.firstChild) {
            this.elements.syncPhase.removeChild(this.elements.syncPhase.firstChild);
        }
        this.updateSyncPhase(phase);
        
        // Update progress bar
        const percentage = syncProgress.percentage || 0;
        this.elements.progressText.textContent = `${percentage}%`;
        this.elements.progressFill.style.width = `${percentage}%`;
        
        // Update details
        this.elements.syncDetails.textContent = syncProgress.message || syncProgress.details || 'No details available';
        
        // Update conditional displays
        this.updateConditionalDisplay(
            this.elements.subPhaseContainer,
            syncProgress.sub_phase,
            this.elements.syncSubPhase
        );
        
        this.updateConditionalDisplay(
            this.elements.peerAddressContainer,
            syncProgress.peer_address,
            this.elements.syncPeerAddress
        );
        
        this.updateConditionalDisplay(
            this.elements.syncErrorContainer,
            syncProgress.error,
            this.elements.syncError
        );
    }
    
    /**
     * Update blockchain statistics section
     */
    updateBlockchainStats(kaspadData, blockdagData) {
        const blockCount = blockdagData.blockCount || 0;
        const headerCount = blockdagData.headerCount || 0;
        const mempoolSize = kaspadData.mempoolSize || 0;
        
        this.elements.blockCount.textContent = blockCount === 0 ? '0 (syncing)' : this.formatNumber(blockCount);
        this.elements.headerCount.textContent = headerCount === 0 ? '0 (syncing)' : this.formatNumber(headerCount);
        this.elements.blueScore.textContent = this.formatNumber(blockdagData.blueScore || 0);
        this.elements.difficulty.textContent = this.formatNumber(blockdagData.difficulty || 0);
        this.elements.mempoolSize.textContent = mempoolSize === 0 ? '0 (syncing)' : this.formatNumber(mempoolSize);
    }
    
    /**
     * Update network statistics section
     */
    updateNetworkStats(peersData) {
        this.elements.connectedPeers.textContent = peersData.peerCount || 0;
        this.elements.peerDirection.textContent = `${peersData.outboundPeers || 0} / ${peersData.inboundPeers || 0}`;
        this.elements.ibdPeers.textContent = peersData.ibdPeers || 0;
        this.elements.averagePing.textContent = peersData.averagePing ? `${peersData.averagePing}ms` : 'N/A';
        
        if (peersData.peerVersions) {
            this.updatePeerVersions(peersData.peerVersions);
        }
        
        if (peersData.peers) {
            this.updatePeerList(peersData.peers);
        }
    }
    
    /**
     * Handle errors during data fetching
     */
    handleError(error) {
        this.elements.syncStatus.textContent = 'Error';
        this.elements.syncStatus.className = 'error';
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new KaspaDashboard();
});