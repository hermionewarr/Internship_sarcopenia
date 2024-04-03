# Internship_sarcopenia

ESTRO poster discussion: https://www.estro.org/Congresses/ESTRO-2021/911/posterdiscussion10-theinterfaceofphysicsandradiobi/3959/automatedsarcopeniaassessmentintheneckandsurvivala

**Locating_C3: Neck Navigator:**

Neck Navigator is a U-Net model to select the C3 vetebra from the 3D CT scan (NIFTI file).

Below: ground truth (left), C3 prediction (right).

<img src="https://user-images.githubusercontent.com/60819221/135115131-b39765e8-a919-4b53-82a1-166d3b13dadb.png" width="600" height="300">

**Sarcopenia_model: Muscle Mapper:**

An FCN neural network to automatically delineate the paravertebral and sternocleidomastoid muscles at the level of the C3 vertebra. 

(a) the input CT slice, (b) the ground truth, (c) the networks prediction

![pred_vs_gt](https://user-images.githubusercontent.com/60819221/135115254-eaa2a0ab-b22a-465f-a792-edb948959e1d.png)


**Inference:**

A script to apply Neck Navigator and Muscle Mapper to all the patients in a directory and write the extracted muscle characteristics to an excel file.
