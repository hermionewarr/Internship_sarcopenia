#utils
#created: 20/07/2021
#hermione

from math import sqrt
from SimpleITK.SimpleITK import Modulus
import numpy as np
from numpy.core.fromnumeric import argmax
import scipy.ndimage as nd
from scipy.ndimage.measurements import center_of_mass, label
import matplotlib.pyplot as plt
import io
import tensorflow as tf
import torch
import torchvision.transforms as T
import torchvision.io.image as tim
from operator import mul
from collections import deque
from decimal import Decimal

from PIL import Image
from matplotlib.colors import Normalize
from matplotlib import cm
"""
Script with modified losses 
"""
from torch.autograd import Variable
import torch.nn.functional as F
import torch.nn as nn
from functools import reduce
import torch
import torch.nn.functional

#LOSSES
def js_reg(p, q):
    #~ Jensen-Shannon Divergence
    #@params:
    # *pred + target are 1D heatmaps
    assert p.shape == q.shape, 'Predicted heatmap not same shape as target'
    #* JS(P||Q) = 0.5*D(P||M) + 0.5*D(Q||M)
    #*M = 0.5*(P+Q)
    m = 0.5*(p + q)
    return 0.5*kl_reg(p, m) + 0.5*kl_reg(q, m)

def kl_reg(q, p, ndims = 5):
    #~ Kullback-Leibler Divergence
    eps=1e-24
    #* D(P||Q) = P log P/Q 
    #* Add small constant to keep log finite
    unsummed_kl = p *((p+eps).log() - (q+eps).log())
    kl_values = reduce(lambda t, _: t.sum(-1, keepdim=False), range(ndims), unsummed_kl)
    return kl_values

def flat_softmax(inp):
    """Compute the softmax with all but the first two tensor dimensions combined."""
    orig_size = inp.size()
    flat = inp.view(-1, reduce(mul, orig_size[2:]))
    flat = torch.nn.functional.softmax(flat, -1)
    return flat.view(*orig_size)

def sharpen_heatmaps(heatmaps, alpha):
    """Sharpen heatmaps by increasing the contrast between high and low probabilities.
    Example:
        Approximate the mode of heatmaps using the approach described by Equation 1 of
        "FlowCap: 2D Human Pose from Optical Flow" by Romero et al.)::
            coords = soft_argmax(sharpen_heatmaps(heatmaps, alpha=6))
    Args:
        heatmaps (torch.Tensor): Heatmaps generated by the model
        alpha (float): Sharpness factor. When ``alpha == 1``, the heatmaps will be unchanged. Use
        ``alpha > 1`` to actually sharpen the heatmaps.
    Returns:
        The sharpened heatmaps.
    """
    sharpened_heatmaps = heatmaps ** alpha
    sharpened_heatmaps = 100*sharpened_heatmaps
    #sharpened_heatmaps /= sharpened_heatmaps.flatten(2).sum(-1)
    return sharpened_heatmaps

#METRICS
def get_data(path): 
    data = np.load(path, allow_pickle=True)
    #print([*data.keys()])
    inputs = data['inputs']
    targets = data['masks']
    ids = data['ids']
    transforms = data['transforms']
    org_slices = data['org_nos']
    dims = data['dims']
    return (np.array(inputs), np.array(targets), np.array(ids), np.array(transforms), np.array(org_slices), np.array(dims))

def GetSliceNumber(segment):
  slice_number = []
  weights = []
  max_range = len(segment)
  for x in range(0,max_range):
    seg_slice = segment[x,...]
    val = np.sum(seg_slice)
    if val != 0:
      slice_number.append(x)
      weights.append(val)
  return np.round(np.average(slice_number, weights = weights), decimals=3)

def GetTargetCoords(target):
  coords = center_of_mass(target) 
  return coords #z,x,y

def slice_preds(masks):
  slice_nos = []
  for i in range(len(masks)):
    #slice_nos.append(GetTargetCoords(masks[i])[0])
    slice_nos.append(GetSliceNumber(masks[i]))
  return np.array(slice_nos)

def euclid_dis(gts, masks, is_tensor = False):
  #quantifies how far off the network's predictions are
  if is_tensor:
    gt = gts
    msk = masks
    gts = gt.cpu().detach().numpy()[0]
    masks = msk.cpu().detach().numpy()[0]
  distances = []
  for i in range(len(gts)):
    gt_z_coords = GetTargetCoords(gts[i])[0]
    msk_z_coords = GetTargetCoords(masks[i])[0]
    distance = np.abs(gt_z_coords-msk_z_coords)
    if len(gts) == 1: 
      distances = distance
    else: 
      distances.append(distance)
  distances = np.array(distances)
  #print(np.average(distances))
  return distances

def threeD_euclid_diff(gts, msks, dims, transform_info = None):
  mm_distances = []
  distances = []
  pythag_dist = []
  NetPostProcessCoords = np.array(mrofsnart(msks, transform_info))
  GTPostProcessCoords =np.array(mrofsnart(gts, transform_info))
  for j in range(3):
    distances.append(np.abs(GTPostProcessCoords[j] - NetPostProcessCoords[j])) #x,y,z
  distances = np.array(distances)
  #have to do backwards processing on images to use this. or just input coords
  for i in range(len(gts)):
    mm_distance = dims[i]*distances[:,i]
    pythag = pythagoras(mm_distance)

    if (gts.ndim == 3): 
      mm_distances = mm_distance
      pythag_dist = pythag
    else: 
      mm_distances.append(np.array(mm_distance))
      pythag_dist.append(pythag)

      def make_arr(a): 
        return np.round(np.array(a),decimals = 3)
      #output shape of mm_distances (54,3)
  return make_arr(distances), make_arr(mm_distances), make_arr(pythag_dist)

def z_euclid_dist(gts, msks, dims):
  three_diff, three_mm_dist,_ = threeD_euclid_diff(gts, msks, dims)
  return three_diff[0], three_mm_dist[0]

def pythagoras(three_distance):
  pythag = np.sqrt(pow(three_distance[0],2)+pow(three_distance[1],2)+pow(three_distance[2],2))
  return pythag

###*** UNDO PREPROCESSING ***###
def do_it_urself_round(number, decimals = 0, is_array = False):
  float_num = number
  dec_num =  Decimal(str(number))
  Ddecimal = Decimal(str(decimals))
  round_num = round(dec_num, decimals)
  diff = np.abs(dec_num - round_num)
  round_diff = Decimal(str(0.5/(10**decimals)))
  if (diff == round_diff and dec_num >= round_num):
    round_num += (1/(10**(Ddecimal))) 
  if decimals == 0:
    return int(round_num)
  else:
    return float(round_num)

# num = 128.456
# print(do_it_urself_round(num))

def mrofsnart(msks, transforms, shape = 128, test_inds = None):#transforms backwards
    x_arr,y_arr,z_arr = [],[],[]
    
    if test_inds is not None:
        transforms = [transforms[ind] for ind in test_inds]
        
    for i in range(len(msks)):
        #undo scale
        coords = GetTargetCoords(msks[i])
        #print(coords)
        z_coord = (coords[0])*14/16
        #print("Undo Scale: ", coords[0])
        #undo crop
        #eg z crop [46,1] z=12  [[true, crop array] <- crop[zmin, zmax, xmin,...],]
        #print(transforms[i][1])
        z = z_coord + transforms[i][1][0]
        x = (coords[1])*2
        y = (coords[2])*2
        x += transforms[i][1][3]
        y += transforms[i][1][6]
        x_arr.append(x)
        #print("Undo Crop:", z, x, y)
        #undo flip if necessary
        if (transforms[i][0]==True):
            y_shape = transforms[i][1][8]
            y = y_shape - y
        y_arr.append(y)

        if (transforms[i][0]==True):
          z_shape = transforms[i][1][2]
          z = z_shape - z
        #print("Final Coords: ", x,y,z)
        #z_arr.append(do_it_urself_round(z))
    return np.array(x_arr),np.array(y_arr),np.array(z_arr)

#MODEL SETUP
def setup_model(model, checkpoint_dir, device, load_prev = False, load_best = False, eval_mode = False):
  model.to(device)
  if load_prev == True:
    model.load_previous(checkpoint_dir, logger=None)
  if load_best == True:
    model.load_best(checkpoint_dir, logger = None)
  for param in model.parameters():
      param.requires_grad = True
  if eval_mode:
    model.eval()
  return model

#DISPLAYING DATA
def PrintSlice(input, targets, show = False):
    slice_no = GetSliceNumber(targets)
    print("slice no: ", slice_no)
    #print("input shape: ", input.shape)
    plt.imshow(input[slice_no,...], cmap = "gray")
    #for i in range(len(targets)):
        #targets[i,...,0][targets[i,...,0] == 0] = np.nan
    plt.imshow(targets[slice_no,...], cmap = "cool", alpha = 0.5)
    plt.axis('off')
    if show:
      plt.show()
      plt.savefig("Slice.png")

def arrange(input, ax, proj_order):
    #to return the projection in whatever order.
    av = np.average(input, axis = ax)
    mx = np.max(input, axis = ax)
    std = np.std(input, axis=ax)
    ord_list = [mx,av,std]
    ord_list[:] = [ord_list[i] for i in proj_order]
    out = np.stack((ord_list), axis=2)
    return out

def base_projections(inp, msk):
  axi,cor,sag = 0,1,2
  proj_order = [2,1,0]
  axial = arrange(inp, axi, proj_order)
  coronal = arrange(inp, cor, proj_order)
  sagital = arrange(inp, sag, proj_order)
  ax_mask = np.max(msk, axis = axi)
  cor_mask = np.max(msk, axis = cor)
  sag_mask = np.max(msk, axis = sag)
  #flip right way up
  coronal = coronal[::-1]
  sagital = sagital[::-1]
  cor_mask = cor_mask[::-1]
  sag_mask = sag_mask[::-1]
  image = (axial,coronal,sagital)
  mask = (ax_mask,cor_mask, sag_mask)
  return image, mask

def projections(inp, msk, order, type = "numpy", show = False, save_name = None, vmax = None):
  axi,cor,sag = 0,1,2
  proj_order = order
  plt.close('all')
  if type == "tensor":
     inp = inp.cpu().detach().squeeze().numpy()
     msk = msk.cpu().detach().squeeze().numpy().astype(float)
     if len(inp.shape) == 4:
       inp = inp[0]
       msk = msk[0]
  if vmax == None:
    vmax = np.max(msk)
  print(np.max(msk))
  images, masks = base_projections(inp, msk)
  fig = plt.figure(figsize=(150, 50))
  ax = []
  columns = 3
  rows = 1
  for i in range(columns*rows):
    # create subplot and append to ax
    ax.append(fig.add_subplot(rows, columns, i+1) )
    ax[-1].set_title("ax:"+str(i))
    plt.imshow(images[i])
    masks[i][masks[i] == 0.00] = np.nan
    plt.imshow(masks[i], cmap="cool", alpha=0.5)#vmin = 0, vmax = max of gt
    plt.axis('off')
  if save_name is not None:
    plt.savefig("projections" + str(save_name) + ".png")
  if show: 
    plt.show()
  return fig

#classs inbalence
#ratio of no of 1s over no of 0s. averaged
def classRatio(masks):
    ratio = []
    for i in range(len(masks)):
        no_of_0s = (masks[i] == 0).sum()
        no_of_1s = (masks[i] == 1).sum()
        ratio.append(no_of_1s/no_of_0s)
    average_ratio = np.mean(ratio)
    print(average_ratio)
    weights = (1/average_ratio) #penalise the network more harshly for getting it wrong
    print(weights)


def get_mips(array):
  """
  Get whatever type of projection you want - this gets maximum intensity projection
  """
  axial_mip = np.max(array, axis=0)[::-1,:]
  sagittal_mip = np.max(array,axis=2)[::-1,:]
  coronal_mip = np.max(array,axis=1)[::-1,:]

  return (axial_mip, sagittal_mip, coronal_mip)

def array_2_image(array, mode="image", window=450, level=50):
  """
  Convert numpy arrays to PIL images, using window/level for CT and some colourmap for 
  masks/distributions

  This also tries to fix aspect ratio so that the patient isn't squashed into a tiny
  little bar.
  """
  if mode == "image":
      cmap = cm.get_cmap('Greys_r')
      norm = Normalize(vmin=level-window//2, vmax=level+window//2) ## use normalise to apply level and window. 
      ## NB Normalize is equivalent to setting vmin & vmax in plt.imshow

      ## Appky W/L and convert slice to PIL Image
      wld_slice = cmap(norm(array))
      image = Image.fromarray((wld_slice[:, :, :3] * 255).astype(np.uint8))
      
  elif mode == "mask":
      cmap_mask = cm.get_cmap('viridis')
      norm_mask = Normalize(vmin=1, vmax=2) 
      ## these two lines convert the mask into a colour image that PIL will be able to understand

      ## apply class colourmap and convert to PIL Image
      array[array == 0] = np.nan
      transf_mask = cmap_mask(norm_mask(array))
      print(transf_mask.shape)
      image = Image.fromarray((transf_mask[:, :, :3] * 255).astype(np.uint8))
  sizefac = image.size[0] / image.size[1]
  image = image.resize( (int(image.size[1]*sizefac ), int(image.size[0])))
  return image


def make_three_projection(axial, sagittal, coronal):
  """
  Paste together the images side-by-side for display
  """
  dest = Image.new("RGB", (axial.width + sagittal.width + coronal.width, axial.height))
  dest.paste(axial, (0,0))
  dest.paste(sagittal, (axial.width, 0))
  dest.paste(coronal, (axial.width+sagittal.width, 0))

  return dest

def composite_three_panel_images(ct, mask, alpha=0.5):
  """
  Composite the images together with mask semi-transparent over the CT

  The image returned can be saved
  """
    ## Generate mask for compositing - should be informed by alpha (i.e. for alpha=0.5, should be 128 in areas where the masks are)
  compo_mask = np.ones(ct.size[::-1], dtype=np.uint8) * np.uint8(255*alpha) ## default alpha 0.5
  compo_mask[mask == 0] = 255 ## transparent background
  ## This is 255 not zero because it is allowing all of the background through. It's a bit backwards.
  compo_mask_image = Image.fromarray(compo_mask) 
  ## Now create the overlaid image
  compost = Image.composite(ct, mask, compo_mask_image)
  ## Save to specified path
  return compost


def pil_2_tf(pil_image):
  """
  Convert a PIL image to something tensorboard can handle
  """
  return tf.keras.preprocessing.img_to_array(pil_image)

def pil_flow(ct, pred):
  """
  Tie everything together in one call
  """
  act, sct, cct = get_mips(ct) ## chage these if you don't want a MIP
  amask, smask, cmask = get_mips(pred) ## I think this will work with float

  axial_ct_im = array_2_image(act, mode='image')
  sagittal_ct_im = array_2_image(sct, mode='image')
  coronal_ct_im = array_2_image(cct, mode='image')

  threeway_ct = make_three_projection(axial_ct_im, sagittal_ct_im, coronal_ct_im)


  axial_msk_im = array_2_image(amask, mode='mask')
  sagittal_msk_im = array_2_image(smask, mode='mask')
  coronal_msk_im = array_2_image(cmask, mode='mask')

  threeway_msk = make_three_projection(axial_msk_im, sagittal_msk_im, coronal_msk_im)

  composited = composite_three_panel_images(threeway_ct, threeway_msk)

  return pil_2_tf(composited)


def plot_to_image(figure):
  """Converts the matplotlib plot specified by 'figure' to a PNG image and
  returns it. The supplied figure is closed and inaccessible after this call."""
  # Save the plot to a PNG in memory.
  buf = io.BytesIO()
  plt.savefig(buf, format='png')
  # Closing the figure prevents it from being displayed directly inside
  # the notebook.
  plt.close(figure)
  buf.seek(0)
  # Convert PNG buffer to TF image
  image = tf.image.decode_png(buf.getvalue())
  # Add the batch dimension
  image = tf.expand_dims(image, 0)
  return image

def display_input_data(path, type = 'numpy', save_name = 'Tgauss_data', show = False):
  inp_data = get_data(path)
  inps = inp_data[0]
  msks = inp_data[1]
  ids = inp_data[2]
  slice_no_gts = inp_data[4]
  data_size = len(inps)
  #images = []
  #targets = []
  if type == "tensor":
     inp = inps.cpu().detach().squeeze().numpy()
     msk = msks.cpu().detach().squeeze().numpy().astype(float)
       
  fig = plt.figure(figsize=(100, 400))
  ax = []
  columns = 6
  rows = int(1 + data_size/2)
  j=0
  for l in range(0, data_size):
    coords = GetTargetCoords(msks[l])
    slice_no_gt = GetSliceNumber(msks[l])
    image, target = base_projections(inps[l], msks[l])
    id = ids[l]
    slice_no = 128 - np.round(slice_no_gt)
    for i in range(1,4):
      # create subplot and append to ax
      j+=1
      print(l,i)
      label = str(l+1) + ', ID: ' + id
      ax.append(fig.add_subplot(rows, columns, j))
      ax[-1].set_title(label)
      plt.imshow(image[i-1])
      target[i-1][target[i-1] == 0] = np.nan
      plt.imshow(target[i-1], cmap="cool", alpha=0.5)
      #displaying c3
      if (i==1):
        plt.scatter((128-coords[1]), coords[2], c ='r', s=10) #x,y
      elif (i==2):
        plt.scatter((128-coords[1]), (128 - coords[0]), c ='r', s = 10) #x,z
      elif (i==3):
        ax[-1].axhline(slice_no, linewidth=2, c='y')
        ax[-1].text(0, slice_no-5, "C3: " + str(slice_no), color='w')
        plt.scatter(coords[2], (128 - coords[0]), c = 'r', s=10) #y,z
        
      plt.axis('off')
      
  path = '/home/hermione/Documents/Internship_sarcopenia/locating_c3/pic_'
  plt.savefig(path + str(save_name) + '.png')
  print("Saved Figure.")
  return fig

#data_path = '/home/hermione/Documents/Internship_sarcopenia/locating_c3/preprocessed_gauss.npz'
#display_input_data(data_path)

def display_net_test(inps, msks, gts, ids, shape = 128, fold_num = None):
  images, targets, preds = [],[],[]
  data_size = len(inps)
  slice_no_preds = slice_preds(msks)
  slice_no_gts = slice_preds(gts)
  print("test data size: ", data_size)
  for i in range(data_size):
    image, gt = base_projections(inps[i], gts[i])
    images.append(image)
    targets.append(gt)
    _, pred = base_projections(inps[i], msks[i])
    preds.append(pred)
  
  #make the figure
  fig = plt.figure(figsize = (100, 400))
  ax = []
  columns = 6
  rows = (2*data_size)/6
  j = 0
  for l in range(1, data_size + 1):
    image = images[l-1]
    target =  targets[l-1]
    pred = preds[l-1]
    id = ids[l-1]
    slice_pred = shape - np.round(slice_no_preds[l-1]) #upside fucking down dear god
    slice_gt = shape - np.round(slice_no_gts[l-1])
    for i in range(3,4):
      #create gt subplot 
      j+=1
      ax.append(fig.add_subplot(rows, columns, j))
      ax[-1].set_title("GT " + str(l) + ',' + id)
      plt.imshow(image[i-1])
      plt.imshow(target[i-1], cmap="cool", alpha=0.5)
      if (i%3==0):
        ax[-1].axhline(slice_gt, linewidth=2, c='y')
        ax[-1].text(0, slice_gt-5, "C3: " + str(slice_gt), color='w')
      plt.axis('off')
    for i in range(3,4):
      #mask subplot
      j+=1
      ax.append(fig.add_subplot(rows, columns, j))
      ax[-1].set_title("Pred " + str(l) + ',' + id)
      plt.imshow(image[i-1])
      plt.imshow(pred[i-1], cmap="cool", alpha=0.5)
      if (i%3==0):
        ax[-1].axhline(slice_pred, linewidth=2, c='y')
        ax[-1].text(0, slice_pred-5, "C3: "+ str(slice_pred), color='w')
      plt.axis('off')
  if fold_num == None:
    path = '/home/hermione/Documents/Internship_sarcopenia/locating_c3/test_pic'
  else:
    path = f'/home/hermione/Documents/Internship_sarcopenia/locating_c3/model_ouputs_fold{fold_num+1}/test_pic{fold_num+1}'
  plt.savefig(path + '.png')
  return slice_no_preds, slice_no_gts