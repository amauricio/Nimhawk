import { Select, Paper, Stack, Title, Group, Badge, Text, Input, Flex } from "@mantine/core"
import { useEffect, useState } from "react";

//this should be dynamic from the database
const MockPayloads = [
    {
        name: "http",
        description: "HTTP Payload",
        options: [
            {
                name: "Host",
                type: "text",
                description: "Host to connect to",
                value: "127.0.0.1",
                editable: false
            },
            {
                name: "Port",
                type: "text",
                description: "Port to connect to",
                value: "8080",
                editable: false
            }
        ]
    }
]
interface Option {
    name: string;
    type: string;
    description: string;
    value: string;
    editable: boolean;
}

interface StructurePayloadData {
    name: string;
    description: string;
    options: Option[];
}

function Payload({ }) {

    const [payloads, setPayloads] = useState<string[]>([]);
    const [structurePayloadData, setStructurePayloadData] = useState<StructurePayloadData[]>([]);
    const [selectedPayload, setSelectedPayload] = useState<string | null>(null);

    useEffect(() => {
        setPayloads(MockPayloads.map(payload => payload.name));
        setSelectedPayload(MockPayloads[0].name);
    }, []);

    useEffect(() => {
        const payload = getCurrentPayload();
        setStructurePayloadData(payload ? [{
            name: payload.name,
            description: payload.description,
            options: payload.options
        }] : []);
    }, [selectedPayload]);

    const getCurrentPayload = () => {
        return MockPayloads.find(payload => payload.name === selectedPayload);
    }

    const evaluatePayload = (item: StructurePayloadData | undefined) => {
        if (!item) return null;
        return item.options.map((option, index) => (
            <Flex key={index} align="center" gap="sm" w="100%">
                <Text w={100}>{option.name}</Text>
                {(() => {
                    switch (option.type) {
                        case 'text':
                            return <Input w="100%" placeholder={option.description} value={option.value} disabled={!option.editable} />
                        default:
                            return null;
                    }
                })()}
            </Flex>
        ))
    }
    return (
        <Paper p="md" radius="md" withBorder>
            <Stack style={{ marginBottom: 15 }}>
                <Group justify="apart">
                    <Title order={5}>Payload Options</Title>
                </Group>
                <Select
                    label=""
                    data={payloads}
                    disabled={true}
                    value={selectedPayload}
                    onChange={setSelectedPayload}
                />
            </Stack>
            <Paper p="md" radius="md" withBorder>
                <Stack>
                    <Group justify="apart">
                        <Title order={5}>Configuration</Title>
                    </Group>
                    {evaluatePayload(getCurrentPayload())}
                </Stack>
            </Paper>
        </Paper>
    )
}

export default Payload;