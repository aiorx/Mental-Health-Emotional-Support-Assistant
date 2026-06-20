import os

def get_project_root():
    """
    得到项目的路径
    :return:
    """
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    project_root = os.path.dirname(current_dir)
    return project_root

def get_abs_path(relative_path: str):
    """
    得到文件的绝对路径
    :return:
    """
    abs_path = os.path.join(get_project_root(), relative_path)
    return abs_path

if __name__ == '__main__':
    print(get_abs_path(__file__))