# 27/07/2021
# Hermione Warr and Olivia Murray
# consensually stolen and adapted from https://github.com/rrr-uom-projects/3DSegmentationNetwork/blob/master/headHunter

#imports
import os
import torch
import numpy as np
from torch.optim import lr_scheduler
from torch.utils.tensorboard import SummaryWriter
from torch.optim.lr_scheduler import ReduceLROnPlateau
import matplotlib
#matplotlib.use('Agg')
import matplotlib.pyplot as plt
import neckNavigatorUtils as utils
import time
from pytorch_toolbelt import losses as L
from utils import projections, euclid_dis, plot_to_image
import tensorflow as tf

#####################################################################################################
##################################### headHunter trainers ###########################################
#####################################################################################################
class neckNavigator_trainer:
    def __init__(self, model, optimizer, lr_scheduler, device, train_loader, val_loader, logger, checkpoint_dir, max_num_epochs=100,
                num_iterations=1, num_epoch=0, patience=10, iters_to_accumulate=4, best_eval_score=None, load_prev_weights = False, eval_score_higher_is_better=False):
        self.logger = logger
        self.logger.info(model)
        self.model = model
        self.optimizer = optimizer
        self.scheduler = lr_scheduler
        self.device = device
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.checkpoint_dir = checkpoint_dir
        self.max_num_epochs = max_num_epochs
        self.eval_score_higher_is_better = eval_score_higher_is_better
        # initialize the best_eval_score
        if not best_eval_score:
            if eval_score_higher_is_better:
                self.best_eval_score = float('-inf')
            else:
                self.best_eval_score = float('+inf')
        else:
            self.best_eval_score = best_eval_score
        self.patience = patience
        self.epochs_since_improvement = 0
        #tensorboard 
        #scalars
        runs = os.listdir(os.path.join(checkpoint_dir, 'logs'))
        if num_epoch == 0:
            log_dir = os.path.join(checkpoint_dir, 'logs','run_{0}'.format(len(runs)))
            os.makedirs(log_dir)
        else: 
            log_dir = os.path.join(checkpoint_dir, 'logs','run_{0}'.format(len(runs)-1))
        self.writer = SummaryWriter(log_dir = log_dir)
        #fig directory
        self.fig_dir = os.path.join(checkpoint_dir, 'figs')
        try:
            os.mkdir(self.fig_dir)
        except OSError:
            pass
        #self.fig_writer = SummaryWriter(log_dir = self.fig_dir)
        self.fig_writer = tf.summary.create_file_writer(self.fig_dir)
        self.num_iterations = num_iterations
        self.iters_to_accumulate = iters_to_accumulate
        self.load_prev_weights = load_prev_weights
        self.num_epoch = num_epoch
        self.epsilon = 1e-6
        self.scaler = torch.cuda.amp.GradScaler()

    def fit(self):
        self._save_init_state()
        for _ in range(self.num_epoch, self.max_num_epochs):
            # train for one epoch
            t = time.time()
            should_terminate = self.train(self.train_loader)
            print("Epoch trained in " + str(int(time.time()-t)) + " seconds.")
            if should_terminate:
                print("Hit termination condition...")
                break
            self.num_epoch += 1
        self.writer.close()
        return self.num_iterations, self.best_eval_score

    def train(self, train_loader):
        """Trains the model for 1 epoch.
        Args:
            train_loader (torch.utils.data.DataLoader): training data loader
        Returns:
            True if the training should be terminated immediately, False otherwise
        """
        train_losses = utils.RunningAverage()
        improved = False        # for early stopping
        self.model.train()      # set the model in training mode
        for batch_idx, sample in enumerate(train_loader):
            self.logger.info(f'Training iteration {self.num_iterations}. Batch {batch_idx + 1}. Epoch [{self.num_epoch + 1}/{self.max_num_epochs}]')
            ct_im = sample[0].type(torch.FloatTensor)
            h_target = sample[1].type(torch.FloatTensor) 
            # send tensors to GPU
            ct_im = ct_im.to(self.device)
            h_target = h_target.to(self.device)
            
            # forward
            output, loss = self._forward_pass(ct_im, h_target)
            train_losses.update(loss.item(), self._batch_size(ct_im))
               
            # compute gradients and update parameters
            # simulate larger batch sizes using gradient accumulation
            loss = loss/self.iters_to_accumulate

            # Native AMP training step
            self.scaler.scale(loss).backward()
            
            # Every iters_to_accumulate, call step() and reset gradients:
            if self.num_iterations%self.iters_to_accumulate == 0:
                self.scaler.step(self.optimizer)
                self.scaler.update()
                self.optimizer.zero_grad()
                # log stats
                self.logger.info(f'Training stats. Loss: {train_losses.avg}')
                self._log_stats('train', train_losses.avg)

            if self.num_iterations%(3*self.iters_to_accumulate) == 0 and self.num_iterations != 0:
                #write the slice difference between gts and preds
                difference = euclid_dis(h_target, output, is_tensor=True)
                self._log_dist(difference)

                self._log_images(ct_im, output, name = "Training Data")
                #projections(ct_im, output, order=[2,1,0], type="tensor", save_name=self.num_epoch)
            
            self.num_iterations += 1

        # evaluate on validation set
        self.model.eval()
        eval_score = self.validate()

        # adjust learning rate if necessary
        self.scheduler.step(eval_score)

        # log current learning rate in tensorboard
        self._log_lr()

        # remember best validation metric
        is_best = self._is_best_eval_score(eval_score)
        if(is_best):
            improved = True
        
        # save checkpoint
        self._save_checkpoint(is_best)

        # implement early stopping here
        if not improved:
            self.epochs_since_improvement += 1
        if(self.epochs_since_improvement > self.patience):  # Model has not improved for certain number of epochs
            self.logger.info(
                    f'Model not improved for {self.patience} epochs. Finishing training...')
            return True
        return False    # Continue training...
        

    def validate(self):
        self.logger.info('Validating...')
        val_losses = utils.RunningAverage()
        with torch.no_grad():
            for batch_idx, sample in enumerate(self.val_loader):
                self.logger.info(f'Validation iteration {batch_idx + 1}')
                ct_im = sample[0].type(torch.FloatTensor) 
                h_target = sample[1].type(torch.FloatTensor)  
                
                # send tensors to GPU
                ct_im = ct_im.to(self.device)
                h_target = h_target.to(self.device)
                
                output, loss = self._forward_pass(ct_im, h_target)
                val_losses.update(loss.item(), self._batch_size(ct_im))
                
                #write the slice difference between gts and preds
                difference = euclid_dis(h_target, output, is_tensor=True)  
                self._log_images(ct_im, output, name = "Validation Data")
                #projections(ct_im, output, order=[2,1,0], type="tensor", save_name=self.num_epoch)
                

            self._log_dist(difference)      
            self._log_stats('val', val_losses.avg)
            self.logger.info(f'Validation finished. Loss: {val_losses.avg}')
            
            return val_losses.avg

    # functions
    def _forward_pass(self, ct_im, h_target):
        with torch.cuda.amp.autocast():
            # forward pass
            output = self.model(ct_im)
            #print("network output",h_target.shape, torch.max(h_target), torch.min(h_target), torch.unique(h_target))
            # MSE loss contribution - unchanged for >1 targets
            loss = torch.nn.MSELoss()(100*output, 100*h_target)#prob masks
            # for i, param_group in enumerate(self.optimizer.param_groups):
            #     lr = float(param_group['lr'])
            #     print("lr: ", lr)
            #projections(ct_im,h_target,order=[2,1,0], type="tensor")
            #loss = torch.nn.BCEWithLogitsLoss(pos_weight=torch.Tensor([100])).to(self.device)(output, h_target)#masks 0s and 1s
            #loss = L.BinaryFocalLoss()(output, h_target)
            #loss = torch.nn.KLDivLoss()(output, h_target)
            #loss = L.JointLoss(L.BinaryFocalLoss(), L.SoftBCEWithLogitsLoss(pos_weight=torch.Tensor([10]).to(self.device)), 1.0, 0.5)(output, h_target)
            #loss = torch.nn.MSELoss().item()
            # L1 loss contribution
            #output = output.cpu()
            #h_target = h_target.cpu()
            # if (output.shape[1] == 1):
            #     # single target case
            #     pred_vox = torch.tensor([np.unravel_index(torch.argmax(output[i, 0]), output.size()[2:]) for i in range(output.size(0))]).type(torch.FloatTensor)
            #     gt_vox = torch.tensor([np.unravel_index(torch.argmax(h_target[i, 0]), h_target.size()[2:]) for i in range(h_target.size(0))]).type(torch.FloatTensor)
            #DSNT here: 
            #loss += (torch.nn.L1Loss()(pred_vox, gt_vox) * 0.01) # scaling factor for the L1 supplementary term
            return output, loss

    def _is_best_eval_score(self, eval_score):
        if self.eval_score_higher_is_better:
            is_best = eval_score > self.best_eval_score
        else:
            is_best = eval_score < self.best_eval_score
        if is_best:
            self.logger.info(f'Saving new best evaluation metric: {eval_score}')
            self._log_new_best(eval_score)
            self.best_eval_score = eval_score
            self.epochs_since_improvement = 0
        return is_best

    def _save_init_state(self):
        state = {'model_state_dict': self.model.state_dict()}
        init_state_path = os.path.join(self.checkpoint_dir, 'initial_state.pytorch')
        self.logger.info(f"Saving initial state to '{init_state_path}'")
        if not os.path.exists(self.checkpoint_dir):
            os.mkdir(self.checkpoint_dir)
        torch.save(state, init_state_path)

    def _save_checkpoint(self, is_best):
        utils.save_checkpoint({
            'epoch': self.num_epoch + 1,
            'num_iterations': self.num_iterations,
            'model_state_dict': self.model.state_dict(),
            'best_eval_score': self.best_eval_score,
            'eval_score_higher_is_better': self.eval_score_higher_is_better,
            #'optimizer_state_dict': self.optimizer.state_dict(),
            'device': str(self.device),
            'max_num_epochs': self.max_num_epochs,
        }, is_best, checkpoint_dir=self.checkpoint_dir,
            logger=self.logger)

    def _log_lr(self):
        lr = self.optimizer.param_groups[0]['lr']
        self.writer.add_scalar('learning_rate', lr, self.num_iterations)

    def _log_new_best(self, eval_score):
        self.writer.add_scalar('best_val_loss', eval_score, self.num_iterations)

    def _log_stats(self, phase, loss_avg):
        tag_value = {
            f'{phase}_loss_avg': loss_avg,
        }
        for tag, value in tag_value.items():
            self.writer.add_scalar(tag, value, self.num_iterations)

    def _log_dist(self, dist):
        self.writer.add_scalar('Slice difference', np.average(dist), self.num_iterations)
    
    def _log_images(self, inp, pred, name):
        images = projections(inp, pred, order=[2,1,0], type="tensor")
        with self.fig_writer.as_default():
            tf.summary.image(name, plot_to_image(images), self.num_iterations)

    def _log_params(self):
        self.logger.info('Logging model parameters and gradients')
        for name, value in self.model.named_parameters():
            self.writer.add_histogram(name, value.data.cpu().numpy(), self.num_iterations)
            #self.writer.add_histogram(name + '/grad', value.grad.data.cpu().numpy(), self.num_iterations) #not sure what this is 

    @staticmethod
    def _batch_size(input):
        if isinstance(input, list) or isinstance(input, tuple):
            return input[0].size(0)
        else:
            return input.size(0)