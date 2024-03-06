import csv
import os
import shutil

import supervisely as sly
from dataset_tools.convert import unpack_if_archive
from supervisely.imaging.color import get_predefined_colors
from supervisely.io.fs import (
    dir_exists,
    file_exists,
    get_file_name,
    get_file_name_with_ext,
    get_file_size,
)
from supervisely.io.json import load_json_file
from tqdm import tqdm

import src.settings as s


def convert_and_upload_supervisely_project(
    api: sly.Api, workspace_id: int, project_name: str
) -> sly.ProjectInfo:
    # Possible structure for bbox case. Feel free to modify as you needs.

    batch_size = 30
    rgb_pathes = "/home/alex/DATASETS/TODO/2v6cgv1x04ol22qp9rm9x2j6a7/GroundTruth-SparseAnnotations/rgb_frames"
    anns_pathes = "/home/alex/DATASETS/TODO/2v6cgv1x04ol22qp9rm9x2j6a7/GroundTruth-SparseAnnotations/annotations"

    classes_path = (
        "/home/alex/DATASETS/TODO/2v6cgv1x04ol22qp9rm9x2j6a7/EPIC_100_noun_classes_v2.csv"
    )

    interpolations_path = (
        "/home/alex/DATASETS/TODO/2v6cgv1x04ol22qp9rm9x2j6a7/Interpolations-DenseAnnotations"
    )

    def create_ann(image_path):
        labels = []
        tags = []

        # image_np = sly.imaging.image.read(image_path)[:, :, 0]
        img_height = 1080
        img_wight = 1920

        if folder == "test":
            video_val = get_file_name(image_path).split("_frame_")[0]
            video = sly.Tag(video_meta, value=video_val)
            tags.append(video)

            return sly.Annotation(img_size=(img_height, img_wight), labels=labels, img_tags=tags)

        tags_data = im_name_to_tags[get_file_name_with_ext(image_path)]
        sub_seq_val, video_val = tags_data
        sub_seq = sly.Tag(sequence_meta, value=sub_seq_val)
        tags.append(sub_seq)

        video = sly.Tag(video_meta, value=video_val)
        tags.append(video)

        id_to_class_name = {}
        ann_data = im_name_to_anns[get_file_name_with_ext(image_path)]
        for curr_ann_data in ann_data:
            obj_class_name = idx_to_class[curr_ann_data["class_id"]]
            id_to_class_name[curr_ann_data["id"]] = obj_class_name

        for curr_ann_data in ann_data:
            l_tags = []
            instance_val = curr_ann_data["name"]
            instance = sly.Tag(instance_meta, value=instance_val)
            l_tags.append(instance)

            if curr_ann_data["exhaustive"] == "y":
                exhaustively = sly.Tag(exhaustively_meta)
                l_tags.append(exhaustively)

            obj_class_name = idx_to_class[curr_ann_data["class_id"]]
            obj_class = meta.get_obj_class(obj_class_name)

            contact = curr_ann_data.get("in_contact_object")
            if contact is not None:
                contact_name = id_to_class_name.get(contact)
                if contact_name is not None:
                    contact_tag = sly.Tag(contact_meta, value=contact_name)
                    l_tags.append(contact_tag)
                else:
                    contact_name = contact.replace("-", " ")
                    contact_tag = sly.Tag(contact_meta, value=contact_name)
                    l_tags.append(contact_tag)

            all_polygons_coords = curr_ann_data["segments"]
            for polygons_coords in all_polygons_coords:
                exterior = []
                for coords in polygons_coords:
                    for i in range(0, len(coords), 2):
                        exterior.append([int(coords[i + 1]), int(coords[i])])
                poligon = sly.Polygon(exterior)
                if poligon.area > 30:
                    label_poly = sly.Label(poligon, obj_class, tags=l_tags)
                    labels.append(label_poly)

        return sly.Annotation(img_size=(img_height, img_wight), labels=labels, img_tags=tags)

    idx_to_class = {}
    with open(classes_path, "r") as file:
        csvreader = csv.reader(file)
        for idx, row in enumerate(csvreader):
            if idx > 0:
                idx_to_class[int(row[0])] = row[1]

    obj_classes = [
        sly.ObjClass(name, sly.Polygon, color)
        for name, color in zip(
            list(idx_to_class.values()), get_predefined_colors(len(list(idx_to_class.values())))
        )
    ]

    sequence_meta = sly.TagMeta("subsequence", sly.TagValueType.ANY_STRING)
    video_meta = sly.TagMeta("video", sly.TagValueType.ANY_STRING)
    instance_meta = sly.TagMeta("instance", sly.TagValueType.ANY_STRING)
    contact_meta = sly.TagMeta("in contact", sly.TagValueType.ANY_STRING)
    exhaustively_meta = sly.TagMeta("exhaustively annotated", sly.TagValueType.NONE)

    project = api.project.create(workspace_id, project_name, change_name_if_conflict=True)
    meta = sly.ProjectMeta(
        obj_classes=obj_classes,
        tag_metas=[sequence_meta, video_meta, instance_meta, contact_meta, exhaustively_meta],
    )
    api.project.update_meta(project.id, meta.to_json())

    im_name_to_anns = {}
    im_name_to_tags = {}
    inter_name_to_anns = {}
    for folder in os.listdir(rgb_pathes):
        path = os.path.join(rgb_pathes, folder)
        if dir_exists(path):
            dataset = api.dataset.create(project.id, folder, change_name_if_conflict=True)
            for subdir in os.listdir(path):
                subpath = os.path.join(path, subdir)
                if dir_exists(subpath):
                    for im_folder in os.listdir(subpath):
                        images_path = os.path.join(subpath, im_folder)
                        if dir_exists(images_path):
                            if folder != "test":
                                ann_json_path = os.path.join(
                                    anns_pathes, folder, im_folder + ".json"
                                )
                                ann = load_json_file(ann_json_path)["video_annotations"]
                                for curr_ann in ann:
                                    im_name_to_anns[curr_ann["image"]["name"]] = curr_ann[
                                        "annotations"
                                    ]
                                    im_name_to_tags[curr_ann["image"]["name"]] = (
                                        curr_ann["image"]["subsequence"],
                                        curr_ann["image"]["video"],
                                    )
                                inter_json_path = os.path.join(
                                    interpolations_path, folder, im_folder + "_interpolations.json"
                                )

                            images_names = os.listdir(images_path)

                            progress = sly.Progress(
                                "Create dataset {}".format(folder), len(images_names)
                            )

                            for images_names_batch in sly.batched(
                                images_names, batch_size=batch_size
                            ):
                                img_pathes_batch = [
                                    os.path.join(images_path, image_name)
                                    for image_name in images_names_batch
                                ]

                                img_infos = api.image.upload_paths(
                                    dataset.id, images_names_batch, img_pathes_batch
                                )
                                img_ids = [im_info.id for im_info in img_infos]

                                anns = [create_ann(image_path) for image_path in img_pathes_batch]
                                api.annotation.upload_anns(img_ids, anns)

                                progress.iters_done_report(len(images_names_batch))

    return project
