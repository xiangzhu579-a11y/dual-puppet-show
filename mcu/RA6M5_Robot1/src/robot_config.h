#ifndef ROBOT_CONFIG_H
#define ROBOT_CONFIG_H

/* Calibrated software command limits, not measured mechanical stops. */
#define ROBOT_AUTOSTART             (0U)
#define ROBOT_BOOT_DELAY_MS         (2000U)
#define ROBOT_HOME_HOLD_MS          (6000U)
#define ROBOT_GROUP_GAP_MS          (20U)
#define ROBOT_SOURCE_FRAME_MS       (120U)
#define ROBOT_MIN_PULSE_US          (500U)
#define ROBOT_MAX_PULSE_US          (2500U)
#define ROBOT_BASE_STOP_US          (1500U)
#define ROBOT_BASE_MIN_US           (1400U)
#define ROBOT_BASE_MAX_US           (1600U)
#define ROBOT_STOP_ON_RX_ERROR      (0U)
#define ROBOT_POSE_OFFSET_US        (100U)
#define ROBOT_JOINT_OFFSETS_US      {100U,100U,0U,100U,200U,100U,200U,200U,200U,100U,200U,200U,100U}
#define ROBOT_ACTION_TARGET_STEP_US (50U)
#define ROBOT_JOINT3_FIXED_US       (500U)
#define ROBOT_JOINT4_MIN_US         (1000U)
#define ROBOT_HOME_PULSES_US        {1000U,2166U,500U,1000U,500U,900U,900U,500U,2000U,500U,1500U,1200U,1500U}

#define ROBOT_RETURN_HOME_MS        (1000U)

#endif
