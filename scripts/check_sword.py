from spatium import Vec3
from sword_mech.sword import Sword


def get_sword():
    s = Sword(Vec3(0, 0, 0), Vec3(0, 0, 10), 0.1)
    print(f"{s.base=}, {s.get_guard_loc()=}, {s.tip=}, {s.get_sword_size()=}")


if __name__ == '__main__':
    get_sword()
