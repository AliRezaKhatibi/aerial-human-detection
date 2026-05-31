# 🚁 Aerial Human Detection

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-ee4c2c.svg)](https://pytorch.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Real-time human detection and tracking in aerial imagery using state-of-the-art deep learning models.**

This project develops a high-performance system for detecting and tracking humans in drone/UAV imagery from altitudes of 30+ meters, achieving real-time inference (10+ FPS) on NVIDIA RTX 3070 hardware.

## ✨ Key Features

- 🎯 **Multiple Detection Models**: YOLO, Faster R-CNN, and SSD implementations
- 🔍 **Object Tracking**: DeepSORT and ByteTrack integration
- ⚡ **Real-time Performance**: Optimized for 10+ FPS on RTX 3070
- 🖥️ **User-Friendly GUI**: Simple interface for model inference
- 📊 **Comprehensive Benchmarking**: Performance comparison across algorithms
- 🐳 **Docker Support**: Containerized deployment ready

## 📋 Project Status

🚧 **Under Development** - Phase 1 (Data Collection & Baseline)

## 🗂 Project Structure

aerial-human-detection/
├── data/ # Datasets and annotations
├── notebooks/ # Research and experimentation
├── src/ # Main source code
│ ├── data/ # Data loading pipeline
│ ├── models/ # Detection and tracking models
│ ├── training/ # Training scripts
│ ├── evaluation/ # Model evaluation
│ ├── inference/ # Real-time inference
│ └── gui/ # User interface
├── configs/ # Model configurations
├── tests/ # Unit and integration tests
├── docs/ # Documentation
└── results/ # Training outputs and reports
