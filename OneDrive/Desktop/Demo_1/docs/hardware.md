# Hardware Targets

For a 10-camera pilot, use a central GPU PC and camera substreams.

## Minimum Practical 10-Camera Setup

| Component | Recommendation |
|---|---|
| CPU | Intel i5-12400/i5-13400 or Ryzen 5 5600+ |
| GPU | RTX 3060 12GB or RTX 4060 8GB |
| RAM | 32GB |
| Storage | 1TB NVMe for app/clips, HDD/NAS only for longer retention |
| Network | Gigabit LAN + PoE switch |
| Camera stream for AI | 640x360 or 720p, 3-5 FPS |

## Bottlenecks

1. GPU inference for YOLO, face recognition, pose, emotion, and object models.
2. CPU video decoding and RTSP stream handling.
3. Disk writes when recording many clips or full video.
4. RAM after 32GB is usually not the main limiter.

## Capacity Estimate

| Setup | Expected optimized cameras |
|---|---:|
| Old CPU-only office PC | 2-3 |
| i5 + RTX 3060/4060 + 32GB | 8-12 |
| i7 + RTX 4070 + 32GB/64GB | 15-25 |

These estimates assume model cadence control, low-resolution AI streams, and
seat-map lookup instead of continuous heavy face recognition.
