import copy
import torch

def federated_averaging(client_models):
    """
    Standard Federated Averaging (FedAvg).
    Averages weight tensors across all local client models.
    """
    global_model = copy.deepcopy(client_models[0])
    global_dict = global_model.state_dict()
    
    for k in global_dict.keys():
        # Average the weights across all clients
        stacked = torch.stack([client.state_dict()[k].float() for client in client_models], dim=0)
        global_dict[k] = torch.mean(stacked, dim=0)
        
    global_model.load_state_dict(global_dict)
    return global_model
