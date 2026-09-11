"""SE(3) frame chain: GNSS/IMU body -> gimbal -> optical centre.

These tests pin *physical meaning*, not algebraic round-trips. A round-trip
passes just as happily with two compensating sign errors; asking "where does a
nadir camera actually look?" does not.
"""
import numpy as np
import pytest

from drishti_recon import frames


def axis(*a, **k):
    return frames.optical_axis_enu(frames.R_enu_from_cam(*a, **k))


class TestOpticalAxisPhysics:
    def test_nadir_looks_straight_down(self):
        # DJI gimbal pitch -90 is straight down
        assert np.allclose(axis(0, -90, 0), [0, 0, -1], atol=1e-9)

    @pytest.mark.parametrize("yaw,expect", [
        (0,   [0, 1, 0]),      # north
        (90,  [1, 0, 0]),      # east
        (180, [0, -1, 0]),     # south
        (270, [-1, 0, 0]),     # west
    ])
    def test_level_camera_follows_compass_heading(self, yaw, expect):
        assert np.allclose(axis(0, 0, yaw), expect, atol=1e-9)

    def test_positive_pitch_looks_up(self):
        # pitch +30 from level must gain altitude component
        assert axis(0, 30, 0)[2] > 0.4

    def test_oblique_45_down_facing_east(self):
        v = axis(0, -45, 90)
        assert v[0] > 0.7 and v[2] < -0.7      # east and downward
        assert abs(v[1]) < 1e-9                # no north component


class TestRotationValidity:
    @pytest.mark.parametrize("rpy", [(0,0,0), (10,-45,120), (-30,15,300)])
    def test_is_a_proper_rotation(self, rpy):
        R = frames.R_enu_from_cam(*rpy)
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-9)
        assert np.isclose(np.linalg.det(R), 1.0, atol=1e-9)

    def test_ned_enu_conversion_is_its_own_inverse(self):
        M = frames.R_ENU_FROM_NED
        assert np.allclose(M @ M, np.eye(3))

    def test_body_from_cam_maps_axes_as_documented(self):
        M = frames.R_BODY_FROM_CAM
        assert np.allclose(M @ [1, 0, 0], [0, 1, 0])   # cam right -> body right
        assert np.allclose(M @ [0, 1, 0], [0, 0, 1])   # cam down  -> body down
        assert np.allclose(M @ [0, 0, 1], [1, 0, 0])   # cam fwd   -> body fwd


class TestGimbalReferencing:
    def test_world_referenced_gimbal_ignores_aircraft_yaw(self):
        """A stabilised gimbal must not swing when the airframe yaws.

        This is the double-counting trap: composing world-referenced gimbal
        angles onto body attitude makes the camera follow the aircraft, which
        is precisely what the gimbal exists to prevent.
        """
        a = axis(0, -90, 0)
        b = axis(0, -90, 0, body_rpy_deg=(0, 0, 137))   # aircraft yawed hard
        assert np.allclose(a, b, atol=1e-9)

    def test_body_referenced_gimbal_does_follow_the_aircraft(self):
        a = axis(0, 0, 0, body_rpy_deg=(0, 0, 0),
                 gimbal_relative_to_body=True)
        b = axis(0, 0, 0, body_rpy_deg=(0, 0, 90),
                 gimbal_relative_to_body=True)
        assert not np.allclose(a, b, atol=1e-6)
        assert np.allclose(b, [1, 0, 0], atol=1e-9)     # now facing east

    def test_body_referenced_without_attitude_raises(self):
        with pytest.raises(ValueError, match="body_rpy_deg"):
            frames.R_enu_from_cam(0, -90, 0, gimbal_relative_to_body=True)

    def test_boresight_tilts_the_axis(self):
        clean = axis(0, -90, 0)
        tilted = axis(0, -90, 0, boresight_rpy_deg=(0, 5, 0))
        ang = np.degrees(np.arccos(np.clip(clean @ tilted, -1, 1)))
        assert 4.5 < ang < 5.5


class TestLeverArm:
    def test_offset_rotates_with_the_aircraft(self):
        gnss = np.zeros((2, 3))
        lever = np.array([1.0, 0.0, 0.0])          # 1 m forward of the antenna
        out, ok = frames.optical_centre_enu(
            gnss, lever, body_rpy_deg=np.array([[0, 0, 0], [0, 0, 90]]))
        assert ok
        assert np.allclose(out[0], [0, 1, 0], atol=1e-9)   # nose north
        assert np.allclose(out[1], [1, 0, 0], atol=1e-9)   # nose east

    def test_body_z_is_down(self):
        out, _ = frames.optical_centre_enu(
            np.zeros((1, 3)), [0, 0, 1.0], body_rpy_deg=[0, 0, 0])
        assert np.allclose(out[0], [0, 0, -1.0], atol=1e-9)

    def test_zero_lever_is_a_noop(self):
        g = np.random.default_rng(0).normal(size=(5, 3))
        out, applied = frames.optical_centre_enu(g, [0, 0, 0],
                                                 body_rpy_deg=[0, 0, 0])
        assert not applied and np.allclose(out, g)

    def test_missing_attitude_declines_rather_than_guessing(self):
        g = np.zeros((3, 3))
        out, applied = frames.optical_centre_enu(g, [1, 0, 0])
        assert not applied and np.allclose(out, g)


class TestExtrinsic:
    def test_world_to_camera_puts_scene_in_front(self):
        C = np.array([0.0, 0.0, 50.0])                 # 50 m up
        R = frames.R_enu_from_cam(0, -90, 0)           # looking down
        T = frames.cam_from_world_matrix(R, C)
        ground = np.array([0.0, 0.0, 0.0, 1.0])
        Xc = T @ ground
        assert Xc[2] > 0                               # positive depth
        assert np.isclose(Xc[2], 50.0, atol=1e-9)
        assert np.allclose(Xc[:2], 0, atol=1e-9)       # on the optical axis

    def test_camera_centre_maps_to_origin(self):
        C = np.array([12.0, -3.0, 40.0])
        T = frames.cam_from_world_matrix(frames.R_enu_from_cam(0, -60, 30), C)
        assert np.allclose((T @ np.append(C, 1.0))[:3], 0, atol=1e-9)
