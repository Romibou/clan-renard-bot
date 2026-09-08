CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id BIGINT PRIMARY KEY,
    timezone TEXT NOT NULL DEFAULT 'Europe/Paris',
    admin_role_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS advent_campaigns (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    year INTEGER NOT NULL CHECK (year BETWEEN 2020 AND 2200),
    title TEXT NOT NULL DEFAULT 'Calendrier de l''Avent',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Europe/Paris',
    opening_hour SMALLINT NOT NULL DEFAULT 0
        CHECK (opening_hour BETWEEN 0 AND 23),
    catchup_mode TEXT NOT NULL DEFAULT 'disabled'
        CHECK (catchup_mode IN ('disabled', 'enabled')),
    channel_id BIGINT,
    announcement_role_id BIGINT,
    announcements_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    day_order SMALLINT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT advent_campaign_dates_valid
        CHECK (end_date >= start_date),

    CONSTRAINT advent_campaign_day_order_size
        CHECK (cardinality(day_order) = 24),

    CONSTRAINT advent_campaign_unique_year
        UNIQUE (guild_id, year)
);


CREATE INDEX IF NOT EXISTS advent_campaigns_guild_index
    ON advent_campaigns (guild_id);

CREATE INDEX IF NOT EXISTS advent_campaigns_enabled_index
    ON advent_campaigns (enabled);


CREATE TABLE IF NOT EXISTS advent_rewards (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL
        REFERENCES advent_campaigns(id)
        ON DELETE CASCADE,
    day SMALLINT NOT NULL CHECK (day BETWEEN 1 AND 24),
    reward_type TEXT NOT NULL
        CHECK (
            reward_type IN (
                'message',
                'points',
                'role',
                'random'
            )
        ),
    reward_data JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT advent_reward_unique_day
        UNIQUE (campaign_id, day)
);


CREATE INDEX IF NOT EXISTS advent_rewards_campaign_index
    ON advent_rewards (campaign_id);


CREATE TABLE IF NOT EXISTS advent_openings (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL
        REFERENCES advent_campaigns(id)
        ON DELETE CASCADE,
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    day SMALLINT NOT NULL CHECK (day BETWEEN 1 AND 24),
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reward_id BIGINT
        REFERENCES advent_rewards(id)
        ON DELETE SET NULL,
    reward_type TEXT NOT NULL,
    reward_snapshot JSONB NOT NULL DEFAULT '{}'::JSONB,
    points_awarded INTEGER NOT NULL DEFAULT 0,
    external_status TEXT NOT NULL DEFAULT 'not_required'
        CHECK (
            external_status IN (
                'not_required',
                'pending',
                'completed',
                'failed'
            )
        ),
    external_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT advent_opening_unique_user_day
        UNIQUE (campaign_id, user_id, day)
);


CREATE INDEX IF NOT EXISTS advent_openings_campaign_user_index
    ON advent_openings (campaign_id, user_id);

CREATE INDEX IF NOT EXISTS advent_openings_campaign_points_index
    ON advent_openings (campaign_id, points_awarded DESC);

CREATE INDEX IF NOT EXISTS advent_openings_guild_index
    ON advent_openings (guild_id);


CREATE TABLE IF NOT EXISTS advent_panels (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL
        REFERENCES advent_campaigns(id)
        ON DELETE CASCADE,
    guild_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT advent_panel_unique_campaign
        UNIQUE (campaign_id)
);


CREATE TABLE IF NOT EXISTS advent_announcements (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL
        REFERENCES advent_campaigns(id)
        ON DELETE CASCADE,
    day SMALLINT NOT NULL CHECK (day BETWEEN 1 AND 24),
    channel_id BIGINT NOT NULL,
    message_id BIGINT,
    announced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT advent_announcement_unique_day
        UNIQUE (campaign_id, day)
);


CREATE TABLE IF NOT EXISTS advent_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    guild_id BIGINT NOT NULL,
    campaign_id BIGINT
        REFERENCES advent_campaigns(id)
        ON DELETE SET NULL,
    actor_id BIGINT,
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS advent_audit_logs_guild_index
    ON advent_audit_logs (guild_id, created_at DESC);
