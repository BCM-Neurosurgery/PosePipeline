import os
import cv2
import numpy as np
from tqdm import tqdm
import datajoint as dj
from pose_pipeline import Video, PersonBbox
from mim import download 

package = 'mmpose'

mmpose_joint_dictionary = {
    'MMPoseWholebody': ["Nose", "Left Eye", "Right Eye", "Left Ear", "Right Ear",
                        "Left Shoulder", "Right Shoulder", "Left Elbow", "Right Elbow",
                        "Left Wrist", "Right Wrist", "Left Hip", "Right Hip", "Left Knee",
                        "Right Knee", "Left Ankle", "Right Ankle", "Left Big Toe",
                        "Left Little Toe", "Left Heel", "Right Big Toe", "Right Little Toe",
                        "Right Heel"],
    'MMPoseHalpe': ["Nose", "Left Eye", "Right Eye", "Left Ear", "Right Ear",
                    "Left Shoulder", "Right Shoulder", "Left Elbow", "Right Elbow",
                    "Left Wrist", "Right Wrist", "Left Hip", "Right Hip", "Left Knee",
                    "Right Knee", "Left Ankle", "Right Ankle", "Head", "Neck",
                    "Pelvis", "Left Big Toe", "Right Big Toe", "Left Little Toe",
                    "Right Little Toe", "Left Heel", "Right Heel"],
    'MMPose': ["Nose", "Left Eye", "Right Eye", "Left Ear", "Right Ear", "Left Shoulder",
                   "Right Shoulder", "Left Elbow", "Right Elbow", "Left Wrist", "Right Wrist",
                   "Left Hip", "Right Hip", "Left Knee", "Right Knee", "Left Ankle", "Right Ankle"]
}

def normalize_scores(scores):
    max_score = np.max(scores)

    if max_score == 0:
        return scores
    
    return scores / max_score

def mmpose_top_down_person(key, method='HRNet_W48_COCO'):

    from mmpose.apis import init_model as init_pose_estimator
    from mmpose.apis import inference_topdown
    from tqdm import tqdm

    from pose_pipeline import MODEL_DATA_DIR

    if method == 'HRNet_W48_COCO':
        pose_cfg = os.path.join(MODEL_DATA_DIR, "mmpose/config/top_down/darkpose/coco/hrnet_w48_coco_384x288_dark.py")
        pose_ckpt = os.path.join(MODEL_DATA_DIR, "mmpose/checkpoints/hrnet_w48_coco_384x288_dark-e881a4b6_20210203.pth")
        num_keypoints = 17
    elif method == 'HRFormer_COCO':
        pose_cfg = os.path.join(MODEL_DATA_DIR, "mmpose/config/top_down/hrformer_base_coco_384x288.py")
        pose_ckpt = os.path.join(MODEL_DATA_DIR, "mmpose/checkpoints/hrformer_base_coco_384x288-ecf0758d_20220316.pth")
        num_keypoints = 17
    elif method == 'HRNet_W48_COCOWholeBody':
        pose_cfg = os.path.join(MODEL_DATA_DIR, "mmpose/config/coco-wholebody/hrnet_w48_coco_wholebody_384x288_dark_plus.py")
        pose_ckpt = os.path.join(MODEL_DATA_DIR, "mmpose/checkpoints/hrnet_w48_coco_wholebody_384x288_dark-f5726563_20200918.pth")
        num_keypoints = 133
    elif method == 'HRNet_TCFormer_COCOWholeBody':
        pose_cfg = os.path.join(MODEL_DATA_DIR, "mmpose/config/coco-wholebody/tcformer_coco_wholebody_256x192.py")
        pose_ckpt = os.path.join(MODEL_DATA_DIR, "mmpose/checkpoints/tcformer_coco-wholebody_256x192-a0720efa_20220627.pth")
        num_keypoints = 133
    elif method == 'HRNet_W48_HALPE':
        pose_cfg = os.path.join(MODEL_DATA_DIR, "mmpose/config/halpe/hrnet_w48_halpe_384x288_dark_plus.py")
        pose_ckpt = os.path.join(MODEL_DATA_DIR, 'mmpose/checkpoints/hrnet_w48_halpe_384x288_dark_plus-d13c2588_20211021.pth')
        num_keypoints = 136
    elif method == 'RTMPose_coco-wholebody':

        # Define the model config and checkpoint files
        pose_config_id = "rtmpose-l_8xb32-270e_coco-wholebody-384x288"
        pose_checkpoint = "rtmpose-l_simcc-coco-wholebody_pt-aic-coco_270e-384x288-eaeb96c8_20230125.pth"

        # define the destination folder
        destination = os.path.join(MODEL_DATA_DIR, f"mmpose/{method}/")

        # download the model and checkpoints
        download(package, [pose_config_id], dest_root=destination)

        # define the model config and checkpoints paths
        pose_cfg = os.path.join(destination, f"{pose_config_id}.py")
        pose_ckpt = os.path.join(destination, pose_checkpoint)

        num_keypoints = 133

    elif method == 'RTMPose_Cocktail14':

        # Define the model config and checkpoint files
        pose_config_id = "rtmw-l_8xb320-270e_cocktail14-384x288"
        pose_checkpoint = "rtmw-dw-x-l_simcc-cocktail14_270e-384x288-20231122.pth"

        # define the destination folder
        destination = os.path.join(MODEL_DATA_DIR, f"mmpose/{method}/")

        # download the model and checkpoints
        download(package, [pose_config_id], dest_root=destination)

        # define the model config and checkpoints paths
        pose_cfg = os.path.join(destination, f"{pose_config_id}.py")
        pose_ckpt = os.path.join(destination, pose_checkpoint)

        num_keypoints = 133
    
    print(f"processing {key}")
    bboxes = (PersonBbox & key).fetch1("bbox")
    video =  Video.get_robust_reader(key, return_cap=False) # returning video allows deleting it
    cap = cv2.VideoCapture(video)

    model = init_pose_estimator(pose_cfg, pose_ckpt)

    results = []
    scores = []
    visibility = []

    for bbox in tqdm(bboxes):

        # should match the length of identified person tracks
        ret, frame = cap.read()
        assert ret and frame is not None

        # handle the case where person is not tracked in frame
        if np.any(np.isnan(bbox)):
            results.append(np.zeros((num_keypoints, 2)))
            scores.append(np.zeros(num_keypoints))
            visibility.append(np.zeros(num_keypoints))
            continue

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        res = inference_topdown(model, frame, np.array(bbox)[None],'xywh')[0]

        keypoints = res.pred_instances.keypoints[0]
        keypoint_confidences = res.pred_instances.keypoint_scores[0]
        keypoint_visibility = res.pred_instances.keypoints_visible[0]

        results.append(keypoints)
        scores.append(keypoint_confidences)
        visibility.append(keypoint_visibility)

    # Convert results to a numpy array
    results = np.asarray(results)

    # Convert scores to a numpy array
    scores = np.asarray(scores)
    # Normalize the score by dividing by the maximum score
    norm_scores = normalize_scores(scores)

    # Convert visibility to a numpy array
    visibility = np.asarray(visibility)

    # Add the normalized scores to the results
    results = np.concatenate([results, norm_scores[..., None]], axis=-1)

    cap.release()
    os.remove(video)

    return results, scores, visibility


def mmpose_bottom_up(key):

    from mmpose.apis import init_pose_model, inference_bottom_up_pose_model
    from tqdm import tqdm

    from pose_pipeline import MODEL_DATA_DIR

    pose_cfg = os.path.join(MODEL_DATA_DIR, "mmpose/config/bottom_up/higherhrnet/coco/higher_hrnet48_coco_512x512.py")
    pose_ckpt = os.path.join(MODEL_DATA_DIR, "mmpose/checkpoints/higher_hrnet48_coco_512x512-60fedcbc_20200712.pth")

    pose_cfg = "/home/jcotton/projects/pose/mmpose/configs/body/2d_kpt_sview_rgb_img/associative_embedding/coco/mobilenetv2_coco_512x512.py"
    pose_ckpt = os.path.join(MODEL_DATA_DIR, "mmpose/checkpoints/mobilenetv2_coco_512x512-4d96e309_20200816.pth")

    model = init_pose_model(pose_cfg, pose_ckpt)

    video = Video.get_robust_reader(key, return_cap=False)
    cap = cv2.VideoCapture(video)

    video_length = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    keypoints = []
    for frame_id in tqdm(range(video_length)):

        # should match the length of identified person tracks
        ret, frame = cap.read()
        assert ret and frame is not None

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        res = inference_bottom_up_pose_model(model, frame)[0]

        kps = np.stack([x["keypoints"] for x in res], axis=0)
        keypoints.append(kps)

    cap.release()
    os.remove(video)

    return np.asarray(keypoints)
