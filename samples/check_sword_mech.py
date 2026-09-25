
def check_game():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    sword_pos = pygame.Vector2(400, 300)
    target_pos = pygame.Vector2(400, 300)
    last_vector = pygame.Vector2(0, -1)

    SENSITIVITY = 0.08
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Fetch DualSense Data
        gyro_pitch = ds.state.gyro.Pitch
        gyro_yaw = ds.state.gyro.Yaw

        # Update target position based on gyroscope
        target_pos.x += gyro_yaw * SENSITIVITY
        target_pos.y += gyro_pitch * SENSITIVITY

        # Compute delta vectors
        delta = target_pos - sword_pos
        distance = delta.length()

        if distance > 0:
            current_vector = delta.normalize()

            # Calculate Dot Product for Sharp Angles
            dot_product = current_vector.dot(last_vector)

            # Check modifiers (L1 for Guard)
            is_guard = ds.state.L1

            if dot_product < 0.3 and not is_guard:
                # IZOLOM PENALTY: Sharp turn detected, blade stalls
                speed_modifier = 0.05
                color = (255, 0, 0)  # Red = Broken Flow
            else:
                speed_modifier = 1.0
                color = (0, 255, 0)  # Green = Flow Engaged

            # Smoothly move physical sword position toward target (Lerp)
            inertia = 0.05 if is_guard else 0.2
            sword_pos += delta * (inertia * speed_modifier)

            if distance > 2:
                last_vector = current_vector

        # Render Frame
        screen.fill((20, 20, 20))
        pygame.draw.circle(screen, (100, 100, 100), (int(target_pos.x), int(target_pos.y)), 5, 1)  # Gyro target
        pygame.draw.circle(screen, color, (int(sword_pos.x), int(sword_pos.y)), 12)  # Physical blade tip

        pygame.display.flip()
        clock.tick(100)

    ds.close()
    pygame.quit()

