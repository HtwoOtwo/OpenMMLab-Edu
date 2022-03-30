import os
import json
import mmcv
import time
from mmcv import Config
from mmdet.apis import inference_detector, init_detector, show_result_pyplot, train_detector
from mmdet.models import build_detector
from mmdet.datasets import build_dataset
from mmcv.runner import load_checkpoint



class MMDetection:
    def __init__(self, 
        backbone='FasterRCNN',
        num_classes=-1,
        dataset_path = None
        ):

        # 获取外部运行py的绝对路径
        self.cwd = os.path.dirname(os.getcwd())
        # 获取当前文件的绝对路径
        self.file_dirname = os.path.dirname(os.path.abspath(__file__))

        self.config = os.path.join(self.file_dirname, 'models', 'FasterRCNN/FasterRCNN.py')
        self.checkpoint = os.path.join(self.file_dirname, 'models', '/FasterRCNN/FasterRCNN.pth')
        
        self.backbone = backbone
        backbone_path = os.path.join(self.file_dirname, 'models', self.backbone)
        ckpt_cfg_list = list(os.listdir(backbone_path))
        for item in ckpt_cfg_list:
            if item[-1] == 'y':
                self.config = os.path.join(backbone_path, item)
            elif item[-1] == 'h':
                self.checkpoint = os.path.join(backbone_path, item)
            else:
                print("Warning!!! There is an unrecognized file in the backbone folder.")

        self.cfg = Config.fromfile(self.config)

        self.dataset_path = dataset_path
        self.lr = None
        self.backbonedict = {
            "FasterRCNN": os.path.join(self.file_dirname, 'models', 'FasterRCNN/FasterRCNN.py'),
            "Yolov3": os.path.join(self.file_dirname, 'models', 'Yolov3/Yolov3.py'),
            # 下略
        }
        self.num_classes = num_classes


    def train(self, random_seed=0, save_fold=None, distributed=False, validate=True,
              metric='bbox', optimizer="SGD", epochs=100, lr=0.001, weight_decay=0.001, Frozen_stages=1,
              checkpoint = None):
        
        # 加载网络模型的配置文件
        self.cfg = Config.fromfile(self.backbonedict[self.backbone])
        print("进行了cfg的切换")

        # 如果外部不指定save_fold
        if not self.save_fold:
            # 如果外部也没有传入save_fold，我们使用默认路径
            if not save_fold:
                self.save_fold = os.path.join(self.cwd, 'checkpoints/det_model')
            # 如果外部传入save_fold，我们使用传入值
            else:
                self.save_fold = save_fold

        self.cfg.model.backbone.frozen_stages = Frozen_stages

        if self.num_classes != -1:
            self.cfg.model.roi_head.bbox_head.num_classes = self.num_classes

        self.load_dataset(self.dataset_path)
        # 添加需要进行检测的类名
        self.cfg.classes = self.get_classes(self.cfg.data.train.ann_file)
        # 分别为训练、测试、验证添加类名
        self.cfg.data.train.classes = self.cfg.classes
        self.cfg.data.test.classes = self.cfg.classes
        self.cfg.data.val.classes = self.cfg.classes

        # 进行
        self.cfg.work_dir = self.save_fold
        # 创建工作目录
        mmcv.mkdir_or_exist(os.path.abspath(self.cfg.work_dir))
        # 创建分类器
        datasets = [build_dataset(self.cfg.data.train)]
        model = build_detector(self.cfg.model, train_cfg=self.cfg.get('train_cfg'), test_cfg=self.cfg.get('test_cfg'))
        if not checkpoint:
            model.init_weights()
        else:
            load_checkpoint(model, checkpoint)

        model.CLASSES = self.cfg.classes
        # 根据输入参数更新config文件
        self.cfg.optimizer.lr = lr  # 学习率
        self.cfg.optimizer.type = optimizer  # 优化器
        self.cfg.optimizer.weight_decay = weight_decay  # 优化器的衰减权重
        self.cfg.evaluation.metric = metric  # 验证指标
        self.cfg.runner.max_epochs = epochs  # 最大的训练轮次

        # 设置每 5 个训练批次输出一次日志
        # self.cfg.log_config.interval = 1
        self.cfg.gpu_ids = range(1)

        self.cfg.seed = random_seed

        train_detector(
            model,
            datasets,
            self.cfg,
            distributed=distributed,
            validate=validate,
            timestamp=time.strftime('%Y%m%d_%H%M%S', time.localtime()),
            meta=dict()
        )

        
    def inference(self, device='cpu',
                  pretrain_model=None,
                  is_trained=False,
                  infer_data=None, show=True, rpn_threshold=0.5, rcnn_threshold=0.3,
        ):
        if not pretrain_model:
            pretrain_model = os.path.join(self.cwd, 'checkpoints/det_model/latest.pth')

        print("========= begin inference ==========")

        if self.num_classes != -1:
            self.cfg.model.roi_head.bbox_head.num_classes = self.num_classes

        checkpoint = self.checkpoint
        if is_trained:
            # 加载数据集及配置文件的路径
            checkpoint = pretrain_model
            self.load_dataset(self.dataset_path)
            # 修正检测的目标
            self.cfg.classes = self.get_classes(self.cfg.data.train.ann_file)
            self.cfg.data.train.classes = self.cfg.classes
            self.cfg.data.test.classes = self.cfg.classes
            self.cfg.data.val.classes = self.cfg.classes
            model.CLASSES = self.cfg.classes
        model = init_detector(self.cfg, checkpoint, device=device)
        model.test_cfg.rpn.nms.iou_threshold = 1 - rpn_threshold
        model.test_cfg.rcnn.nms.iou_threshold = 1 - rcnn_threshold

        img_array = mmcv.imread(infer_data)
        result = inference_detector(model, img_array) # 此处的model和外面的无关,纯局部变量
        if show == True:
            show_result_pyplot(model, infer_data, result)
        return result


    def load_dataset(self, path):
        self.dataset_path = path

        #数据集修正为coco格式
        self.cfg.data.train.img_prefix = os.path.join(self.dataset_path, 'images/train/')
        print(self.cfg.data.train.img_prefix)
        self.cfg.data.train.ann_file = os.path.join(self.dataset_path, 'annotations/train.json')

        self.cfg.data.val.img_prefix = os.path.join(self.dataset_path, 'images/test/')
        self.cfg.data.val.ann_file = os.path.join(self.dataset_path, 'annotations/valid.json')

        self.cfg.data.test.img_prefix = os.path.join(self.dataset_path, 'images/test/')
        self.cfg.data.test.ann_file = os.path.join(self.dataset_path, 'annotations/valid.json')


    def get_classes(self, annotation_file):
        classes = ()
        with open(annotation_file, 'r') as f:
            dataset = json.load(f)
            # categories = dataset["categories"]
            if 'categories' in dataset:
                for cat in dataset['categories']:
                    classes = classes + (cat['name'],)
        return classes

        
       