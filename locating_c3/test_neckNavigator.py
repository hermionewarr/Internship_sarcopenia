#created by hermione on 16/08/2021
#to test the model at various stages

from torch.nn.functional import fold
from utils import get_data, mrofsnart, euclid_dis, pythagoras, threeD_euclid_diff, display_net_test, slice_preds, GetSliceNumber
from neckNavigatorTester import neckNavigatorTest2

from neckNavigator import neckNavigator
from neckNavigatorData import neckNavigatorDataset
from torch.utils.data import DataLoader
import numpy as np
import torch
#from neckNavigatorUtils import k_fold_split_train_val_test
from neckNavigatorTrainerUtils import k_fold_cross_val
import pandas as pd 


def main():

    # get data
    #data_path =  '/home/olivia/Documents/Internship_sarcopenia/locating_c3/preprocessed_Tgauss.npz'
    #data_path = '/home/hermione/Documents/Internship_sarcopenia/locating_c3/preprocessed_Tgauss.npz'
    save_path = '/home/hermione/Documents/Internship_sarcopenia/locating_c3/fold_info/c3_loc.xlsx'#' +str(i) + '
    checkpoint = "/home/hermione/Documents/Internship_sarcopenia/locating_c3/model_ouputs"
    xl_writer = pd.ExcelWriter(save_path)

    # data = get_data(data_path)
    # inputs = data[0]
    # targets = data[1]
    # ids = data[2]
    # transforms = data[3]
    # org_slices = data[4]
    # voxel_dims = data[5]

    # test_workers = int(4)

    # allocate ims to train, val and test
    #dataset_size = len(inputs)
    #train_array, test_array = k_fold_cross_val(dataset_size, num_splits = 5)

    for i in range(0,5):

        ###*** LOAD SAVED PREDICTIONS ***###
        model_dir = checkpoint + "_fold" + str(i+1)
        net_data_path = model_dir + "/trained_net_tests.npz"
        fold_data = np.load(net_data_path, allow_pickle=True)
        #images = C3s, preds = segments, gts = GTs, index = test_inds, ids = test_ids, 
            #test_processing = test_processing_info, test_preprocessed_gt_slices = test_org_slices, test_vox_dims = test_vox_dims)
        C3s = fold_data['images']
        segments = fold_data['preds']
        GTs = fold_data['gts']
        test_inds = fold_data['index']
        test_ids = fold_data['ids']
        test_processing_info = fold_data['test_processing']
        test_org_slices = fold_data['test_preprocessed_gt_slices']
        test_vox_dims = fold_data['test_vox_dims']
        #test_inds = test_array[i]

        #test_dataset = neckNavigatorDataset(inputs = inputs, targets = targets, im_inds = test_inds)
        #test_dataloader = DataLoader(dataset= test_dataset, batch_size = 1, shuffle=False, pin_memory=True, num_workers=test_workers, worker_init_fn=lambda _: np.random.seed(int(torch.initial_seed())%(2**32-1)))
        #print(test_inds)
        #model_dir = "/home/hermione/Documents/Internship_sarcopenia/locating_c3/model_ouputs_fold" +f'{(i+1)}'
        


        #device = 'cuda:1'

        #tester = neckNavigatorTest2(model_dir, test_dataloader, device)#load_best = true
        #C3s, segments, GTs = tester

        slice_no_preds, slice_no_gts = display_net_test(C3s, segments, GTs, test_ids, fold_num = i)

        print("Net Preds: ",slice_no_preds.shape)
        
        # test_org_slices = org_slices[test_inds]
        # test_vox_dims = voxel_dims[test_inds]
        # test_processing_info = transforms[test_inds]
        # test_ids = ids[test_inds]

        #####*** POST-PROCESSING ***#####
        slice_no_preds = slice_preds(segments)  
        slice_no_gts = slice_preds(GTs)
        x,y,z = mrofsnart(segments, test_processing_info)
        _,_,z_test  = mrofsnart(GTs, test_processing_info)

        three_difference, three_mm_distance, pythagoras = threeD_euclid_diff(GTs, segments, test_vox_dims)
        
        ###*** SAVING TEST INFO ***###
        df = pd.DataFrame({"IDs": test_ids, "Out_Slice_Numbers": slice_no_preds, "GT_ProcessedSliceNo": slice_no_gts, "PostProcessSliceNo": z, 
        "GT_Org_Slice_No": test_org_slices, "GT_z_test": z_test,"SliceDifference": three_difference[0] ,"SliceDistances": three_mm_distance[0], 
            "x_distance": three_mm_distance[1], "y_disance": three_mm_distance[2], "pythag_dist_abs": pythagoras})
        df.to_excel(excel_writer = xl_writer, index=False,
                sheet_name=f'fold{i+1}')
        xl_writer.save()
        
    xl_writer.close()


    return

if __name__ == '__main__':
    main()