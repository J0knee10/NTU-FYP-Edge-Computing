import torch
import torch.nn as nn

class TinyAutoencoder(nn.Module):
    """
    Ultra-lightweight MLP Autoencoder designed for on-device Cortex-M microcontrollers.
    Parameter count: ~1,500 parameters (Under 6KB in float32, under 1.5KB in INT8).
    SRAM activation footprint: < 1KB.
    """
    def __init__(self, input_dim=22, latent_dim=4):
        super(TinyAutoencoder, self).__init__()
        # Encoder: compresses input features into a low-dimensional bottleneck
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 12),
            nn.ReLU(),
            nn.Linear(12, latent_dim),
            nn.ReLU()
        )
        # Decoder: reconstructs baseline features from the latent code
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 12),
            nn.ReLU(),
            nn.Linear(12, input_dim)
        )
        
    def forward(self, x):
        z = self.encoder(x)
        out = self.decoder(z)
        return out
    
    def compute_anomaly_score(self, x):
        """Computes Mean Squared Error (MSE) reconstruction loss per sample."""
        with torch.no_grad():
            x_hat = self.forward(x)
            mse = torch.mean((x - x_hat) ** 2, dim=-1)
        return mse
