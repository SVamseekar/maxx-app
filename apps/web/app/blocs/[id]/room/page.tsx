import Room from "./room";
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <Room id={(await params).id}/>;
}
