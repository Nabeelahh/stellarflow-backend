export enum PacketPriority {
    CRITICAL = 0,
    STANDARD = 1,
    METRIC = 2, // Historical tracing metrics
}

export interface IngestionPacket {
    priority: PacketPriority;
    data: any;
    timestamp: number;
}

export class BackpressureManager {
    private queue: IngestionPacket[] = [];
    private readonly MAX_CAPACITY = 1000; // Adjust based on your memory constraints
    private readonly DROP_THRESHOLD = 0.9; // 90% threshold

    /**
     * Adds a packet to the ingestion stream with drop-tail logic.
     */
    public enqueue(packet: IngestionPacket): boolean {
        const saturation = this.queue.length / this.MAX_CAPACITY;

        if (saturation >= this.DROP_THRESHOLD) {
            // Drop-tail strategy: Reject non-essential metrics when saturated
            if (packet.priority === PacketPriority.METRIC) {
                console.warn(`[Backpressure] Saturation at ${Math.round(saturation * 100)}%. Dropping metric packet.`);
                return false;
            }
        }

        if (this.queue.length >= this.MAX_CAPACITY) {
            // Hard limit reached: Only allow critical packets if there's room, 
            // or drop standard packets to make space (Optional refinement)
            console.error("[Backpressure] Queue overflow. Dropping packet.");
            return false;
        }

        this.queue.push(packet);
        return true;
    }

    public dequeue(): IngestionPacket | undefined {
        return this.queue.shift();
    }

    public getQueueLength(): number {
        return this.queue.length;
    }
}