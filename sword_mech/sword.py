import spatium as sp


class Sword:
    base: sp.Vec3
    tip: sp.Vec3
    len_to_guard_proportion: float # len to len_to_guard_proportion from base
    __sword_len: float = None

    def __init__(self, base: sp.Vec3, tip: sp.Vec3, len_to_guard_proportion: float):
        self.__check_sword(base, tip, len_to_guard_proportion)
        self.base = base
        self.tip = tip
        self.len_to_guard_proportion = len_to_guard_proportion
        self._set_sword_len()

    @staticmethod
    def __check_sword(base: sp.Vec3, tip: sp.Vec3, len_to_guard_proportion: float):
        assert 0.05 < len_to_guard_proportion < 0.5

    def _set_sword_len(self):
        self.__sword_len = self.base | self.tip

    def get_guard_loc(self):
        base_to_tip_dir = self.tip - self.base
        return self.base + base_to_tip_dir * self.len_to_guard_proportion

    def get_sword_size(self):
        return self.__sword_len
