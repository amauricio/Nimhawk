import { Badge, useMantineTheme } from "@mantine/core";
import { Group } from "@mantine/core";
import { Switch, Title, Stack, Paper, Text } from "@mantine/core";
import { useState, useEffect } from "react";
interface DebugOptionProps {
    disabled: boolean;
    onCheckedChange: (isDebug: boolean) => void;
}

function DebugOption({ disabled, onCheckedChange }: DebugOptionProps) {
    const theme = useMantineTheme();
    const [isDebug, setIsDebug] = useState(false);

    useEffect(() => {
        onCheckedChange(isDebug);
    }, [isDebug]);

    return (
        <Paper p="md" radius="md" withBorder>
            <Stack>
                <Title order={5}>Build Options</Title>

                <Switch
                    checked={isDebug}
                    onChange={(e) => setIsDebug(e.currentTarget.checked)}
                    label={
                        <Group>
                            <Text>Debug Mode</Text>
                            {isDebug && <Badge color="orange" size="xs">Debug</Badge>}
                        </Group>
                    }
                    description="Compiles with additional debugging information"
                    disabled={disabled}
                    styles={{
                        label: { fontWeight: 500 },
                        thumb: {
                            backgroundColor: isDebug ? '#fff' : undefined,
                        },
                        track: {
                            backgroundColor: isDebug ? theme.colors.orange[6] : undefined
                        }
                    }}
                    size="md"
                    color={isDebug ? "orange" : "dark"}
                />
            </Stack>
        </Paper>
    )
}

export default DebugOption;