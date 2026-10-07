import os
import sys
import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

# Add src to sys.path
sys.path.append(os.path.abspath('.'))

from src.features.vibration_features import load_cwru_mat, window_signal
from src.models.autoencoder import TinyAutoencoder
from src.federated.fed_avg import federated_averaging

def run_stage1_simulation():
    print("==========================================================")
    print("   STAGE 1: PC SIMULATOR FOR EDGE AI VIBRATION DETECTOR   ")
    print("==========================================================")
    
    data_dir = os.path.join('data', 'raw')
    
    # 1. Load Data
    print("\n[Step 1] Loading CWRU Bearing Data...")
    sig_normal_0hp = load_cwru_mat(os.path.join(data_dir, 'normal_0hp.mat'))
    sig_normal_1hp = load_cwru_mat(os.path.join(data_dir, 'normal_1hp.mat'))
    sig_fault_inner = load_cwru_mat(os.path.join(data_dir, 'fault_inner_race.mat'))
    sig_fault_ball  = load_cwru_mat(os.path.join(data_dir, 'fault_ball.mat'))
    sig_fault_outer = load_cwru_mat(os.path.join(data_dir, 'fault_outer_race.mat'))
    
    print(f"Normal 0HP samples: {len(sig_normal_0hp)}")
    print(f"Normal 1HP samples: {len(sig_normal_1hp)}")
    
    # 2. Extract Features (Time + FFT Bins)
    print("\n[Step 2] Extracting Lightweight Features (Time + FFT Bins)...")
    feats_normal_0hp = window_signal(sig_normal_0hp)
    feats_normal_1hp = window_signal(sig_normal_1hp)
    feats_fault_inner = window_signal(sig_fault_inner)
    feats_fault_ball = window_signal(sig_fault_ball)
    feats_fault_outer = window_signal(sig_fault_outer)
    
    print(f"Extracted feature shape (normal 0HP): {feats_normal_0hp.shape}")
    
    # Normalize features using scaler fitted on normal baseline
    scaler = StandardScaler()
    feats_normal_0hp = scaler.fit_transform(feats_normal_0hp)
    feats_normal_1hp = scaler.transform(feats_normal_1hp)
    feats_fault_inner = scaler.transform(feats_fault_inner)
    feats_fault_ball = scaler.transform(feats_fault_ball)
    feats_fault_outer = scaler.transform(feats_fault_outer)
    
    input_dim = feats_normal_0hp.shape[1]
    
    # 3. Simulate On-Device Local Burn-in (Client 1: 0HP, Client 2: 1HP)
    print("\n[Step 3] Simulating On-Device Burn-in on 2 Distributed Edge Devices...")
    client1 = TinyAutoencoder(input_dim=input_dim, latent_dim=4)
    client2 = TinyAutoencoder(input_dim=input_dim, latent_dim=4)
    
    def train_client(model, data, epochs=30, lr=0.005):
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        criterion = nn.MSELoss()
        tensor_data = torch.tensor(data, dtype=torch.float32)
        model.train()
        for ep in range(epochs):
            optimizer.zero_grad()
            pred = model(tensor_data)
            loss = criterion(pred, tensor_data)
            loss.backward()
            optimizer.step()
        return loss.item()
    
    loss1 = train_client(client1, feats_normal_0hp)
    loss2 = train_client(client2, feats_normal_1hp)
    print(f"Client 1 (Motor 0HP) Local Burn-in Loss: {loss1:.6f}")
    print(f"Client 2 (Motor 1HP) Local Burn-in Loss: {loss2:.6f}")
    
    # 4. Federated Aggregation (FedAvg)
    print("\n[Step 4] Running Federated Aggregation (FedAvg) over Simulated Fleet...")
    global_model = federated_averaging([client1, client2])
    print("Global Model successfully aggregated from distributed edge weights!")
    
    # 5. Anomaly Detection Benchmark on Global Model
    print("\n[Step 5] Evaluating Fault Detection on Unseen Fault Data...")
    
    def eval_anomaly(model, normal_data, fault_data, fault_name):
        model.eval()
        t_normal = torch.tensor(normal_data, dtype=torch.float32)
        t_fault = torch.tensor(fault_data, dtype=torch.float32)
        
        score_normal = model.compute_anomaly_score(t_normal).numpy()
        score_fault  = model.compute_anomaly_score(t_fault).numpy()
        
        y_true = np.concatenate([np.zeros_like(score_normal), np.ones_like(score_fault)])
        y_scores = np.concatenate([score_normal, score_fault])
        auc = roc_auc_score(y_true, y_scores)
        
        print(f"[{fault_name}] Normal MSE: {np.mean(score_normal):.4f} | Fault MSE: {np.mean(score_fault):.4f} | Detection AUC: {auc*100:.2f}%")
        return auc
        
    auc_inner = eval_anomaly(global_model, feats_normal_0hp, feats_fault_inner, "Inner Race Fault")
    auc_ball  = eval_anomaly(global_model, feats_normal_0hp, feats_fault_ball,  "Ball Bearing Fault")
    auc_outer = eval_anomaly(global_model, feats_normal_0hp, feats_fault_outer, "Outer Race Fault")
    
    print("\n==========================================================")
    print(f"STAGE 1 BENCHMARK RESULT: Average Detection AUC = {np.mean([auc_inner, auc_ball, auc_outer])*100:.2f}%")
    print("==========================================================")

if __name__ == '__main__':
    run_stage1_simulation()
