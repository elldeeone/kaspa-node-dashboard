/**
 * Kaspa Node Dashboard JavaScript
 * Handles real-time data fetching and UI updates
 */

class KaspaDashboard {
    constructor() {
        this.updateInterval = 5000; // 5 seconds
        this.MAX_PEERS = 16; // Maximum expected peer connections
        this.phases = ['IBD Negotiation', 'Headers Proof IBD', 'Block Download', 'Finalization'];
        
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
            connectionStatus: document.getElementById('connectionStatus'),
            connectionIndicator: document.getElementById('connectionIndicator'),
            
            // Sync progress elements
            syncPhaseIndicator: document.getElementById('syncPhaseIndicator'),
            syncSubPhase: document.getElementById('syncSubPhase'),
            subPhaseContainer: document.getElementById('subPhaseContainer'),
            progressText: document.getElementById('progressText'),
            syncDetails: document.getElementById('syncDetails'),
            syncPeerAddress: document.getElementById('syncPeerAddress'),
            peerAddressContainer: document.getElementById('peerAddressContainer'),
            syncError: document.getElementById('syncError'),
            syncErrorContainer: document.getElementById('syncErrorContainer'),
            
            // Blockchain stats elements
            mempoolSize: document.getElementById('mempoolSize'),
            
            // Peer overview elements
            connectedPeers: document.getElementById('connectedPeers'),
            peerDirection: document.getElementById('peerDirection'),
            ibdPeers: document.getElementById('ibdPeers'),
            averagePing: document.getElementById('averagePing'),
            peerList: document.getElementById('peerList'),
            
            // New elements for redesigned layout
            outboundCount: document.getElementById('outboundCount'),
            inboundCount: document.getElementById('inboundCount'),
            radialProgress: document.getElementById('radialProgress'),
            
            // Update time
            lastUpdate: document.getElementById('lastUpdate')
        };
    }
    
    /**
     * Initialize the dashboard
     */
    init() {
        this.initializeRadialProgress();
        this.initializeSyncPhaseIndicator();
        this.fetchData();
        setInterval(() => this.fetchData(), this.updateInterval);
    }
    
    /**
     * Initialize radial progress component
     */
    initializeRadialProgress() {
        const container = this.elements.radialProgress;
        const circumference = 2 * Math.PI * 45;
        
        container.innerHTML = `
            <svg class="absolute inset-0" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="45" class="text-zinc-800" stroke="currentColor" stroke-width="10" fill="none" />
                <circle
                    cx="50"
                    cy="50"
                    r="45"
                    class="text-teal-400"
                    stroke="currentColor"
                    stroke-width="10"
                    fill="none"
                    stroke-linecap="round"
                    stroke-dasharray="${circumference}"
                    stroke-dashoffset="${circumference}"
                    transform="rotate(-90 50 50)"
                    id="radialProgressCircle"
                />
            </svg>
            <div class="flex flex-col items-center text-center">
                <span class="text-4xl font-bold text-gray-50" id="radialProgressValue">0</span>
                <span class="text-sm text-zinc-400">Peers</span>
            </div>
        `;
    }
    
    /**
     * Update radial progress
     */
    updateRadialProgress(value, max = this.MAX_PEERS) {
        const circumference = 2 * Math.PI * 45;
        const progress = value / max;
        const strokeDashoffset = circumference * (1 - progress);
        
        const circle = document.getElementById('radialProgressCircle');
        const valueElement = document.getElementById('radialProgressValue');
        
        if (circle && valueElement) {
            circle.style.strokeDashoffset = strokeDashoffset;
            valueElement.textContent = value;
        }
    }
    
    /**
     * Initialize sync phase indicator
     */
    initializeSyncPhaseIndicator() {
        this.updateSyncPhaseIndicator('IBD Negotiation');
    }
    
    /**
     * Update sync phase indicator
     */
    updateSyncPhaseIndicator(currentPhase, isComplete = false) {
        const container = this.elements.syncPhaseIndicator;
        const currentIndex = this.phases.indexOf(currentPhase);
        
        let html = '';
        this.phases.forEach((phase, index) => {
            const isCompleted = isComplete || index < currentIndex;
            const isCurrent = !isComplete && index === currentIndex;
            
            html += `
                <div class="flex flex-col items-center gap-2">
                    <div class="relative flex h-8 w-8 items-center justify-center rounded-full border-2 transition-all duration-300 ${
                        isCompleted ? 'border-teal-400 bg-teal-400' : 'border-zinc-600'
                    } ${isCurrent ? 'border-teal-400' : ''}">
                        ${isCompleted ? '<svg class="h-5 w-5 text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>' : ''}
                        ${isCurrent ? '<span class="absolute h-full w-full animate-ping rounded-full bg-teal-400 opacity-75"></span><div class="h-3 w-3 rounded-full bg-teal-400"></div>' : ''}
                    </div>
                    <p class="text-center text-xs font-medium transition-colors duration-300 ${
                        isCompleted || isCurrent ? 'text-gray-200' : 'text-zinc-500'
                    }">${phase}</p>
                </div>
            `;
            
            if (index < this.phases.length - 1) {
                html += `
                    <div class="relative top-4 mx-2 h-0.5 flex-1 rounded-full transition-colors duration-300 ${
                        isCompleted ? 'bg-teal-400' : 'bg-zinc-600'
                    }"></div>
                `;
            }
        });
        
        container.innerHTML = html;
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
     * Format sub-phase names to be human readable
     */
    formatSubPhase(subPhase) {
        if (!subPhase) return '';
        
        // Convert snake_case to Title Case
        return subPhase
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
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
            container.innerHTML = '<tr><td colspan="5" class="text-center text-zinc-400 py-8">No peers connected</td></tr>';
            return;
        }
        
        // Clear existing content
        container.innerHTML = '';
        
        peers.forEach(peer => {
            const row = document.createElement('tr');
            row.className = 'border-b border-zinc-800 hover:bg-zinc-800/50';
            
            const version = peer.version.includes('kaspad:') ? 
                peer.version.split('kaspad:')[1].split('/')[0] : 
                peer.version;
                
            const pingColor = peer.ping > 1000 ? 'text-red-400' : 
                             peer.ping > 500 ? 'text-yellow-400' : 'text-green-400';
            
            const directionBadge = peer.is_outbound ? 
                '<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border border-teal-500/50 bg-teal-500/10 text-teal-400">OUT</span>' :
                '<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border border-purple-500/50 bg-purple-500/10 text-purple-400">IN</span>';
            
            // Add IBD tag if this is an IBD peer
            const ibdTag = peer.is_ibd ? 
                '<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border border-orange-500/50 bg-orange-500/10 text-orange-400 ml-1">IBD</span>' : '';
            
            const peerAddress = `${peer.ip}:${peer.port}`;
            
            row.innerHTML = `
                <td class="py-3 px-2 font-mono text-sm text-zinc-300">${peerAddress}${ibdTag}</td>
                <td class="py-3 px-2">
                    <span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-zinc-700 text-zinc-300">
                        v${version}
                    </span>
                </td>
                <td class="py-3 px-2 text-center">${directionBadge}</td>
                <td class="py-3 px-2 text-right font-medium ${pingColor}">${peer.ping}ms</td>
                <td class="py-3 px-2 text-right text-zinc-400 text-sm">${this.formatDuration(peer.connected_time)}</td>
            `;
            
            container.appendChild(row);
        });
    }
    
    /**
     * Map sync phase from API to display phase
     */
    mapSyncPhase(apiPhase) {
        if (!apiPhase || apiPhase.toLowerCase() === 'complete' || apiPhase.includes('Synchronized')) {
            return 'Finalization';
        }
        if (apiPhase.includes('Negotiation')) {
            return 'IBD Negotiation';
        }
        if (apiPhase.includes('Headers') || apiPhase.includes('Proof')) {
            return 'Headers Proof IBD';
        }
        if (apiPhase.includes('Block') || apiPhase.includes('Download')) {
            return 'Block Download';
        }
        return 'IBD Negotiation'; // Default fallback
    }
    
    /**
     * Update conditional display elements
     */
    updateConditionalDisplay(container, value, textElement, isSubPhase = false) {
        if (value) {
            container.style.display = 'flex';
            if (isSubPhase) {
                textElement.textContent = this.formatSubPhase(value);
            } else {
                textElement.textContent = typeof value === 'string' ? value : value.replace(/_/g, ' ');
            }
        } else {
            container.style.display = 'none';
        }
    }
    
    /**
     * Main data fetching and update function
     */
    async fetchData() {
        try {
            // First check connection status
            const connectionResponse = await fetch('/api/info/connection');
            if (connectionResponse.ok) {
                const connectionData = await connectionResponse.json();
                this.updateConnectionStatus(connectionData);
            }
            
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
            
            // Update connection status to show we're connected and receiving data
            this.updateConnectionStatus({ connected: true, ready: true });
            
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
        const status = kaspadData.isSynced ? 'Running' : 'Syncing';
        this.elements.syncStatus.textContent = status;
        this.elements.syncStatus.className = kaspadData.isSynced ? 'text-teal-400' : 'text-yellow-400';
        
        const version = kaspadData.version || 'Unknown';
        this.elements.version.textContent = version === 'Unknown' ? version : `v${version}`;
        
        const p2pId = kaspadData.p2pId || 'Unknown';
        this.elements.p2pId.textContent = `P2P ID: ${p2pId}`;
        this.elements.p2pId.title = `Click to copy P2P ID: ${p2pId}`;
        
        // Add click handler for P2P ID copying
        this.elements.p2pId.onclick = () => {
            if (p2pId !== 'Unknown') {
                navigator.clipboard.writeText(p2pId).then(() => {
                    // Brief visual feedback
                    const originalText = this.elements.p2pId.textContent;
                    this.elements.p2pId.textContent = 'P2P ID: Copied!';
                    this.elements.p2pId.style.color = '#10b981';
                    setTimeout(() => {
                        this.elements.p2pId.textContent = originalText;
                        this.elements.p2pId.style.color = '';
                    }, 1000);
                }).catch(() => {
                    console.log('Failed to copy P2P ID');
                });
            }
        };
        
        this.elements.network.textContent = kaspadData.networkName || 'Unknown';
        
        const uptime = kaspadData.uptime?.uptime_formatted || 'Unknown';
        this.elements.uptime.textContent = uptime.includes('for') ? uptime : `for ${uptime}`;
        
        // Update UTXO indexed status
        const utxoElement = this.elements.utxoIndexed;
        if (kaspadData.hasUtxoIndex) {
            utxoElement.textContent = 'Yes';
            utxoElement.className = 'inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border border-teal-500/50 bg-teal-500/10 text-teal-400';
        } else {
            utxoElement.textContent = 'No';
            utxoElement.className = 'inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border border-red-500/50 bg-red-500/10 text-red-400';
        }
    }
    
    /**
     * Update sync progress section
     */
    updateSyncProgress(syncProgress) {
        const phase = syncProgress.phase || 'Unknown';
        const mappedPhase = this.mapSyncPhase(phase);
        const percentage = syncProgress.percentage || 0;
        
        // Check if sync is complete
        const isComplete = percentage >= 100 && (phase.toLowerCase() === 'complete' || phase.includes('Synchronized'));
        
        // Update phase indicator with completion status
        this.updateSyncPhaseIndicator(mappedPhase, isComplete);
        
        // Update progress percentage with special handling for 100%
        if (isComplete) {
            this.elements.progressText.textContent = '100% Synced';
        } else {
            this.elements.progressText.textContent = `${percentage}%`;
        }
        
        // Update details
        this.elements.syncDetails.textContent = syncProgress.message || syncProgress.details || 'No details available';
        
        // Update conditional displays with proper formatting
        this.updateConditionalDisplay(
            this.elements.subPhaseContainer,
            syncProgress.sub_phase,
            this.elements.syncSubPhase,
            true // isSubPhase = true for formatting
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
        const mempoolSize = kaspadData.mempoolSize || 0;
        const isSynced = kaspadData.isSynced || false;
        
        if (mempoolSize === 0) {
            this.elements.mempoolSize.textContent = isSynced ? '0' : '0 (syncing)';
        } else {
            this.elements.mempoolSize.textContent = this.formatNumber(mempoolSize);
        }
    }
    
    /**
     * Update network statistics section
     */
    updateNetworkStats(peersData) {
        const peerCount = peersData.peerCount || 0;
        const outbound = peersData.outboundPeers || 0;
        const inbound = peersData.inboundPeers || 0;
        
        this.elements.connectedPeers.textContent = peerCount;
        this.elements.peerDirection.textContent = `${outbound} Out / ${inbound} In`;
        this.elements.ibdPeers.textContent = `${peersData.ibdPeers || 0} IBD peers`;
        this.elements.averagePing.textContent = peersData.averagePing ? `${peersData.averagePing}ms` : 'N/A';
        
        // Update new elements
        this.elements.outboundCount.textContent = outbound;
        this.elements.inboundCount.textContent = inbound;
        
        // Update radial progress
        this.updateRadialProgress(peerCount, this.MAX_PEERS);
        
        if (peersData.peers) {
            this.updatePeerList(peersData.peers);
        }
    }
    
    /**
     * Update connection status indicator
     */
    updateConnectionStatus(status) {
        if (!this.elements.connectionStatus || !this.elements.connectionIndicator) return;
        
        if (status.connected && status.ready) {
            // Fully connected and ready
            this.elements.connectionStatus.textContent = 'Connected';
            this.elements.connectionIndicator.className = 'w-2 h-2 rounded-full bg-green-500';
            this.elements.connectionIndicator.title = 'WebSocket connected and ready';
        } else if (status.connected && !status.ready) {
            // Connected but not ready (still initializing)
            this.elements.connectionStatus.textContent = 'Initializing...';
            this.elements.connectionIndicator.className = 'w-2 h-2 rounded-full bg-yellow-500 animate-pulse';
            this.elements.connectionIndicator.title = 'WebSocket connected, initializing';
        } else {
            // Not connected
            this.elements.connectionStatus.textContent = 'Disconnected';
            this.elements.connectionIndicator.className = 'w-2 h-2 rounded-full bg-red-500 animate-pulse';
            this.elements.connectionIndicator.title = 'WebSocket disconnected, retrying...';
        }
        
        // Show subscription status if available
        if (status.subscribed) {
            this.elements.connectionStatus.textContent += ' (Live)';
        }
    }
    
    /**
     * Handle errors during data fetching
     */
    handleError(error) {
        this.elements.syncStatus.textContent = 'Error';
        this.elements.syncStatus.className = 'error';
        
        // Update connection status to show disconnected
        this.updateConnectionStatus({ connected: false, ready: false });
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new KaspaDashboard();
});