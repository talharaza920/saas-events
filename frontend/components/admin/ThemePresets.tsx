"use client";

import { useEffect, useState } from "react";

import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { adminApi, type ThemePreset } from "@/lib/adminApi";

/**
 * The curated looks a couple can start from (AI_WIZARD_PLAN 8.5e).
 *
 * Presentational on purpose: picking a card only tells ThemePanel which preset
 * is pending, so the editor above can fill with its colours and fonts and the
 * couple can see the look before anything is saved. The panel's one Save button
 * then applies it (server-side, by id) and layers any hand edits on top — a
 * preset is a starting point, never a lock.
 */
export default function ThemePresets({
  selectedId,
  onSelect,
  disabled,
}: {
  selectedId: string | null;
  onSelect: (preset: ThemePreset) => void;
  disabled?: boolean;
}) {
  const [presets, setPresets] = useState<ThemePreset[] | null>(null);

  useEffect(() => {
    let live = true;
    adminApi
      .themePresets()
      .then((p) => live && setPresets(p))
      // A catalogue that won't load must not take the hand editor down with it.
      .catch(() => live && setPresets([]));
    return () => {
      live = false;
    };
  }, []);

  if (presets === null) return <Skeleton variant="rounded" height={104} sx={{ mb: 3 }} />;
  if (presets.length === 0) return null; // no catalogue → just the hand editor

  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle2" color="text.secondary">
        Start from a theme
      </Typography>
      <Typography variant="caption" color="text.secondary">
        Pick one to try it on. It replaces the colours and fonts below — which you
        can then change. Nothing is saved until you press Save.
      </Typography>
      <Stack direction="row" spacing={1.5} sx={{ overflowX: "auto", pt: 1.5, pb: 1 }}>
        {presets.map((preset) => {
          const active = preset.id === selectedId;
          return (
            <Card
              key={preset.id}
              variant="outlined"
              sx={{
                flex: "0 0 auto",
                width: 172,
                borderColor: active ? "primary.main" : "divider",
                borderWidth: 2,
                borderStyle: "solid",
              }}
            >
              <CardActionArea
                data-testid={`theme-preset-${preset.id}`}
                disabled={disabled}
                onClick={() => onSelect(preset)}
                sx={{ p: 1.5, height: "100%", alignItems: "flex-start" }}
              >
                <Stack direction="row" spacing={0.5} sx={{ mb: 1 }}>
                  {preset.swatches.map((hex, i) => (
                    <Box
                      key={`${preset.id}-${i}`}
                      sx={{
                        width: 18,
                        height: 18,
                        borderRadius: "50%",
                        bgcolor: hex,
                        border: "1px solid",
                        borderColor: "divider",
                      }}
                    />
                  ))}
                </Stack>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {preset.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {preset.description}
                </Typography>
              </CardActionArea>
            </Card>
          );
        })}
      </Stack>
    </Box>
  );
}
